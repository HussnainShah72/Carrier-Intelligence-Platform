"""
Module 5 - the structured voice interview engine.

This is the heart of the project.  One turn of the interview does, in order:

   1. (caller) local Whisper transcribes the candidate's recording
   2. analyse the answer locally in ~1 ms   (answer_analysis.py)
   3. decide stage, follow-up and effective difficulty  (stages.py)
   4. stream the interviewer's reply from the LLM
   5. as soon as the FIRST SENTENCE is complete, send it to local Piper and
      emit the audio -- without waiting for the rest of the reply
   6. keep streaming text + audio sentence by sentence
   7. record every timestamp so Module 7 can report real latency

Step 5 is the whole reason the engine is written as a generator: the assignment
asks for the time from the end of the candidate's speech to the start of the
interviewer's reply, and the only way to make that small is to begin speaking
before generation finishes.

The generator yields plain dicts which the API layer forwards as
Server-Sent Events.
"""

from __future__ import annotations

import base64
import re
import time
from dataclasses import dataclass, field
from typing import Any, Iterator, Sequence

from app.core.config import settings
from app.core.errors import LLMError, NotFoundError, SpeechError, ValidationError
from app.core.db import dumps, execute, loads, new_id, query_all, query_one, utcnow
from app.core.logging_setup import get_logger
from app.services.interview import stages as stage_mod
from app.services.interview.answer_analysis import (
    AnswerAnalysis,
    adapt_difficulty,
    analyse_answer,
    coverage_note,
    should_follow_up,
)
from app.services.interview.rubric import DIFFICULTIES
from app.services.llm import json_guard
from app.services.llm.client import LLMClient, get_llm
from app.services.llm.prompts import (
    DIFFICULTY_NOTES,
    INTERVIEW_PLAN_SYSTEM,
    INTERVIEW_SYSTEM_TEMPLATE,
    candidate_context_block,
    interview_plan_prompt,
    interview_turn_prompt,
    role_context_block,
)
from app.services.metrics import recorder as metrics
from app.services.speech import tts

log = get_logger(__name__)

MODE_VOICE = "voice"
MODE_TEXT = "text"

STATUS_ACTIVE = "active"
STATUS_COMPLETE = "complete"
STATUS_ABANDONED = "abandoned"

SPEAKER_INTERVIEWER = "interviewer"
SPEAKER_CANDIDATE = "candidate"


@dataclass
class TurnTimings:
    """Every timestamp the performance report needs, in one place."""

    stt_ms: float | None = None
    llm_ttft_ms: float | None = None
    llm_total_ms: float | None = None
    tts_first_ms: float | None = None
    tts_total_ms: float | None = None
    e2e_first_audio_ms: float | None = None
    total_ms: float | None = None
    audio_seconds: float | None = None
    chars_out: int = 0
    tts_engine: str = ""
    stt_engine: str = ""
    llm_provider: str = ""
    llm_model: str = ""

    def to_dict(self) -> dict[str, Any]:
        def ms(value: float | None) -> float | None:
            return round(value, 1) if value is not None else None

        return {
            "stt_ms": ms(self.stt_ms),
            "llm_ttft_ms": ms(self.llm_ttft_ms),
            "llm_total_ms": ms(self.llm_total_ms),
            "tts_first_ms": ms(self.tts_first_ms),
            "tts_total_ms": ms(self.tts_total_ms),
            "e2e_first_audio_ms": ms(self.e2e_first_audio_ms),
            "total_ms": ms(self.total_ms),
            "audio_seconds": round(self.audio_seconds, 2) if self.audio_seconds is not None else None,
            "chars_out": self.chars_out,
            "tts_engine": self.tts_engine,
            "stt_engine": self.stt_engine,
            "llm_provider": self.llm_provider,
            "llm_model": self.llm_model,
        }


@dataclass
class Interview:
    id: str
    role_title: str
    cv_id: str = ""
    difficulty: str = "medium"
    mode: str = MODE_VOICE
    stage: str = stage_mod.INTRODUCTION
    status: str = STATUS_ACTIVE
    plan: dict[str, Any] = field(default_factory=dict)
    state: stage_mod.StageState = field(default_factory=stage_mod.StageState)
    started_at: str = ""
    ended_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "role_title": self.role_title,
            "cv_id": self.cv_id,
            "difficulty": self.difficulty,
            "mode": self.mode,
            "stage": self.stage,
            "status": self.status,
            "plan": self.plan,
            "progress": stage_mod.progress(self.state, self.difficulty),
            "started_at": self.started_at,
            "ended_at": self.ended_at,
        }


# ===========================================================================
# Creation
# ===========================================================================


def create_interview(
    *,
    role_title: str,
    difficulty: str = "medium",
    mode: str = MODE_VOICE,
    cv_id: str = "",
    cv_profile: dict[str, Any] | None = None,
    role_requirements: dict[str, Any] | None = None,
) -> Interview:
    """Plan and persist a new interview."""
    role_title = (role_title or "").strip()
    if not role_title:
        raise ValidationError("A job role is required to start an interview.")
    if len(role_title) > 120:
        raise ValidationError("That job title is too long (maximum 120 characters).")

    difficulty = difficulty if difficulty in DIFFICULTIES else "medium"
    mode = mode if mode in (MODE_VOICE, MODE_TEXT) else MODE_VOICE

    candidate_context = candidate_context_block(cv_profile or {})
    role_context = role_context_block(role_requirements or {})

    plan = _build_plan(role_title, difficulty, candidate_context, role_context)
    plan["candidate_context"] = candidate_context
    plan["role_context"] = role_context
    plan["role_skills"] = _role_skill_names(role_requirements or {})
    plan["candidate_first_name"] = ((cv_profile or {}).get("full_name") or "").split(" ")[0][:40]

    interview = Interview(
        id=new_id("int"),
        role_title=role_title,
        cv_id=cv_id,
        difficulty=difficulty,
        mode=mode,
        plan=plan,
        started_at=utcnow(),
    )
    interview.state.effective_difficulty = difficulty

    execute(
        "INSERT INTO interviews(id, cv_id, role_title, difficulty, mode, stage, status, plan_json, "
        "state_json, report_json, started_at, ended_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            interview.id, interview.cv_id, interview.role_title, interview.difficulty, interview.mode,
            interview.stage, interview.status, dumps(interview.plan), dumps(interview.state.to_dict()),
            "", interview.started_at, "",
        ),
    )
    log.info("Interview %s created: role=%r difficulty=%s mode=%s",
             interview.id, role_title, difficulty, mode)
    return interview


def _build_plan(role_title: str, difficulty: str, candidate_context: str, role_context: str) -> dict[str, Any]:
    client = get_llm()
    try:
        payload, _ = client.complete_json(
            interview_plan_prompt(role_title, difficulty, candidate_context, role_context),
            system=INTERVIEW_PLAN_SYSTEM,
            task="interview_plan",
            temperature=0.4,
            max_tokens=1200,
        )
    except Exception as exc:
        log.warning("Interview planning failed, using a minimal plan: %s", exc)
        payload = {}

    technical = json_guard.as_str_list(payload.get("technical_topics"), limit=10, max_len=90)
    if not technical:
        technical = ["core technical requirements of the role", "practical experience", "problem solving approach"]

    return {
        "interviewer_name": json_guard.as_text(payload.get("interviewer_name"), default="Alex Morgan", max_len=60),
        "interviewer_persona": json_guard.as_text(
            payload.get("interviewer_persona"),
            default="Hiring manager; practical, asks for concrete examples.",
            max_len=200,
        ),
        "opening_line_hint": json_guard.as_text(
            payload.get("opening_line_hint"),
            default="Greet the candidate, introduce yourself and the role, invite a brief self-introduction.",
            max_len=300,
        ),
        "cv_talking_points": json_guard.as_str_list(payload.get("cv_talking_points"), limit=6, max_len=160),
        "technical_topics": technical,
        "behavioural_themes": json_guard.as_str_list(payload.get("behavioural_themes"), limit=6, max_len=120)
        or ["working with others", "handling a mistake", "prioritising under pressure", "learning something new"],
        "gap_probes": json_guard.as_str_list(payload.get("gap_probes"), limit=5, max_len=90),
        "red_flag_checks": json_guard.as_str_list(payload.get("red_flag_checks"), limit=4, max_len=120),
        "rubric_version": "1.0",
        "llm_degraded": client.is_offline,
    }


def _role_skill_names(requirements: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for key in ("core_technical_skills", "desirable_technical_skills", "tools_and_platforms", "soft_skills"):
        for value in requirements.get(key) or []:
            name = value.get("canonical") if isinstance(value, dict) else str(value)
            if name and name not in names:
                names.append(name)
    for value in requirements.get("combined_skills") or []:
        name = value.get("canonical") if isinstance(value, dict) else str(value)
        if name and name not in names:
            names.append(name)
    return names[:60]


# ===========================================================================
# Persistence
# ===========================================================================


def load_interview(interview_id: str) -> Interview:
    row = query_one("SELECT * FROM interviews WHERE id = ?", (interview_id,))
    if row is None:
        raise NotFoundError("That interview could not be found. It may have been cleared from storage.")

    interview = Interview(
        id=row["id"],
        role_title=row["role_title"],
        cv_id=row["cv_id"],
        difficulty=row["difficulty"],
        mode=row["mode"],
        stage=row["stage"],
        status=row["status"],
        plan=loads(row["plan_json"], {}) or {},
        state=stage_mod.StageState.from_dict(loads(row["state_json"], {}) or {}),
        started_at=row["started_at"],
        ended_at=row["ended_at"],
    )
    interview.state.stage = interview.stage
    return interview


def _save_interview(interview: Interview) -> None:
    execute(
        "UPDATE interviews SET stage=?, status=?, state_json=?, ended_at=? WHERE id=?",
        (interview.stage, interview.status, dumps(interview.state.to_dict()), interview.ended_at, interview.id),
    )


def add_turn(
    interview_id: str,
    *,
    speaker: str,
    stage: str,
    text: str,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = query_one(
        "SELECT COALESCE(MAX(turn_index), -1) AS last FROM interview_turns WHERE interview_id = ?",
        (interview_id,),
    )
    index = int(row["last"]) + 1 if row else 0
    turn_id = new_id("turn")
    created = utcnow()

    execute(
        "INSERT INTO interview_turns(id, interview_id, turn_index, speaker, stage, text, meta_json, created_at) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (turn_id, interview_id, index, speaker, stage, text, dumps(meta or {}), created),
    )
    return {
        "id": turn_id,
        "turn_index": index,
        "speaker": speaker,
        "stage": stage,
        "text": text,
        "meta": meta or {},
        "created_at": created,
    }


def get_turns(interview_id: str) -> list[dict[str, Any]]:
    rows = query_all(
        "SELECT * FROM interview_turns WHERE interview_id = ? ORDER BY turn_index ASC", (interview_id,)
    )
    return [
        {
            "id": r["id"],
            "turn_index": r["turn_index"],
            "speaker": r["speaker"],
            "stage": r["stage"],
            "text": r["text"],
            "meta": loads(r["meta_json"], {}) or {},
            "created_at": r["created_at"],
        }
        for r in rows
    ]


def transcript_text(turns: Sequence[dict[str, Any]], *, limit: int | None = None) -> str:
    selected = list(turns)[-limit:] if limit else list(turns)
    lines: list[str] = []
    for turn in selected:
        label = "Interviewer" if turn["speaker"] == SPEAKER_INTERVIEWER else "Candidate"
        lines.append(f"{label}: {turn['text']}")
    return "\n\n".join(lines)


# ===========================================================================
# The turn
# ===========================================================================


def stream_turn(
    interview_id: str,
    *,
    candidate_text: str = "",
    stt_ms: float | None = None,
    stt_engine: str = "",
    audio_seconds: float | None = None,
    speak: bool = True,
    speech_ended_at: float | None = None,
) -> Iterator[dict[str, Any]]:
    """
    Run one interviewer turn, yielding events as they happen.

    `speech_ended_at` is a perf_counter() reading taken when the candidate's
    audio arrived at the server.  Every end-to-end latency figure is measured
    from it, so the number reported is genuinely "end of speech to first audio",
    not "time the LLM took".

    Events:
      stage       -> stage changed (or confirmed) before generating
      analysis    -> local answer analysis for the previous answer
      text        -> a text delta from the LLM
      audio       -> one base64 WAV chunk (a sentence), with its index
      metrics     -> the full TurnTimings for this turn
      done        -> turn finished, carries the complete reply and progress
      error       -> something failed; message is safe to display
    """
    turn_started = time.perf_counter()
    reference = speech_ended_at if speech_ended_at is not None else turn_started

    interview = load_interview(interview_id)
    if interview.status != STATUS_ACTIVE:
        yield {"type": "error", "code": "interview_finished",
               "message": "This interview has already finished. Start a new one to continue practising."}
        return

    timings = TurnTimings(stt_ms=stt_ms, stt_engine=stt_engine, audio_seconds=audio_seconds)
    state = interview.state
    role_skills = interview.plan.get("role_skills") or []

    # ------------------------------------------------- record the answer ---
    analysis: AnswerAnalysis | None = None
    if candidate_text.strip():
        analysis = analyse_answer(candidate_text, role_skills)
        add_turn(
            interview.id,
            speaker=SPEAKER_CANDIDATE,
            stage=state.stage,
            text=candidate_text.strip(),
            meta={"analysis": analysis.to_dict(), "stt_ms": stt_ms, "stt_engine": stt_engine,
                  "audio_seconds": audio_seconds},
        )

        state.answer_scores.append(round(analysis.quality_score, 3))
        if analysis.quality_band == "strong":
            state.consecutive_strong += 1
            state.consecutive_weak = 0
        elif analysis.quality_band == "weak":
            state.consecutive_weak += 1
            state.consecutive_strong = 0
        else:
            state.consecutive_strong = 0
            state.consecutive_weak = 0

        for skill in analysis.role_skills_mentioned:
            if skill not in state.demonstrated_skills:
                state.demonstrated_skills.append(skill)

        yield {"type": "analysis", "analysis": analysis.to_dict()}

    # --------------------------------------------------- stage management --
    previous_stage = state.stage
    if candidate_text.strip() and stage_mod.should_advance(state, interview.difficulty, candidate_text):
        state.stage_history.append(
            {"stage": state.stage, "questions": state.stage_question_count, "ended_at": utcnow()}
        )
        state.stage = stage_mod.next_stage(state.stage)
        state.stage_question_count = 0
        state.follow_up_depth = 0

        if state.stage == stage_mod.COMPLETE:
            interview.stage = stage_mod.COMPLETE
            interview.status = STATUS_COMPLETE
            interview.ended_at = utcnow()
            interview.state = state
            _save_interview(interview)
            yield {
                "type": "done",
                "finished": True,
                "stage": stage_mod.COMPLETE,
                "reply": "",
                "progress": stage_mod.progress(state, interview.difficulty),
                "message": "The interview is complete. Generating your feedback report.",
            }
            return

    interview.stage = state.stage
    if state.stage != previous_stage:
        yield {
            "type": "stage",
            "stage": state.stage,
            "stage_name": stage_mod.spec_for(state.stage).name,
            "previous_stage": previous_stage,
            "progress": stage_mod.progress(state, interview.difficulty),
        }

    # ------------------------------------------------------- adaptation ----
    state.effective_difficulty = adapt_difficulty(
        interview.difficulty, state.consecutive_strong, state.consecutive_weak
    )
    # Follow-up probing only makes sense in the assessed stages.
    follow_up = (
        should_follow_up(analysis, state.follow_up_depth)
        if analysis and stage_mod.spec_for(state.stage).scored else False
    )
    state.follow_up_depth = state.follow_up_depth + 1 if follow_up else 0

    note = coverage_note(
        analysis,
        uncovered_topics=_uncovered_topics(interview, state),
        follow_up=follow_up,
        effective_difficulty=state.effective_difficulty,
    )

    system_prompt = _system_prompt(interview, state)
    turns = get_turns(interview.id)
    user_prompt = interview_turn_prompt(
        stage=state.stage,
        history_text=transcript_text(turns, limit=settings.interview_history_turns),
        last_answer=candidate_text,
        asked_questions=state.asked_questions,
        coverage_note=note,
    )

    # ---------------------------------------- stream LLM + speak as we go --
    client = LLMClient(model=settings.fast_model if not get_llm().is_offline else None)
    timings.llm_provider = client.provider
    timings.llm_model = client.model

    first_name = interview.plan.get("candidate_first_name", "")
    reply_parts: list[str] = []
    pending = ""
    audio_index = 0
    audio_total_ms = 0.0
    audio_seconds_total = 0.0
    first_audio_done = False
    llm_started = time.perf_counter()

    # The LLM writes every turn, the closing included (the specification says
    # the LLM generates everything). In QA a 3B model ignored "do not ask a
    # question" in the closing, so closing sentences that ask something are
    # dropped before they are spoken (see _drop_sentence).
    closing = state.stage == stage_mod.CLOSING

    def drop(sentence: str) -> bool:
        return _drop_sentence(sentence, first_name, closing=closing)

    try:
        for chunk in client.stream(
            user_prompt,
            system=system_prompt,
            task="interview_turn",
            temperature=0.65,
            max_tokens=320,
        ):
            if chunk.delta:
                if timings.llm_ttft_ms is None:
                    timings.llm_ttft_ms = (time.perf_counter() - reference) * 1000
                reply_parts.append(chunk.delta)
                pending += chunk.delta
                yield {"type": "text", "delta": chunk.delta}

                if speak and interview.mode == MODE_VOICE:
                    sentence, pending = _take_complete_sentence(pending)
                    if sentence and not drop(sentence):
                        for event, elapsed, seconds in _speak(sentence, audio_index, reference):
                            if event.get("type") == "audio":
                                audio_total_ms += elapsed
                                audio_seconds_total += seconds
                                if not first_audio_done:
                                    timings.tts_first_ms = elapsed
                                    timings.e2e_first_audio_ms = (time.perf_counter() - reference) * 1000
                                    first_audio_done = True
                                timings.tts_engine = event.get("engine", timings.tts_engine)
                                audio_index += 1
                            yield event

            if chunk.is_final:
                timings.llm_total_ms = (time.perf_counter() - llm_started) * 1000

    except LLMError as exc:
        log.error("Interview turn LLM failure on %s: %s", interview.id, exc.message)
        interview.state = state
        _save_interview(interview)
        yield {"type": "error", "code": exc.code, "message": exc.message}
        return

    if timings.llm_total_ms is None:
        timings.llm_total_ms = (time.perf_counter() - llm_started) * 1000

    reply = "".join(reply_parts).strip()
    reply = _clean_reply(_strip_speaker_label(reply), first_name, closing=closing)
    # A closing must actually close. If every sentence was a question (fallback
    # used) or what is left never thanks the candidate, add the closing line,
    # and speak it, since none of it was spoken while streaming.
    closing_extra = ""
    if closing and reply == _closing_line(first_name):
        log.info("Closing reply for %s contained only questions; used the fallback line", interview.id)
        closing_extra = reply
    elif closing and "thank" not in reply.lower():
        closing_extra = _closing_line(first_name)
        reply = f"{reply} {closing_extra}".strip()
    if closing_extra:
        pending = f"{pending} {closing_extra}".strip() if not drop(pending) else closing_extra

    if not reply:
        yield {"type": "error", "code": "empty_reply",
               "message": "The interviewer produced no reply. Please try that turn again."}
        interview.state = state
        _save_interview(interview)
        return

    # Speak whatever is left over (the final partial sentence).
    if speak and interview.mode == MODE_VOICE and pending.strip() and not drop(pending):
        for event, elapsed, seconds in _speak(pending, audio_index, reference):
            if event.get("type") == "audio":
                audio_total_ms += elapsed
                audio_seconds_total += seconds
                if not first_audio_done:
                    timings.tts_first_ms = elapsed
                    timings.e2e_first_audio_ms = (time.perf_counter() - reference) * 1000
                    first_audio_done = True
                timings.tts_engine = event.get("engine", timings.tts_engine)
                audio_index += 1
            yield event

    timings.tts_total_ms = audio_total_ms or None
    timings.audio_seconds = audio_seconds_total or audio_seconds
    timings.chars_out = len(reply)
    timings.total_ms = (time.perf_counter() - reference) * 1000

    # -------------------------------------------------------- bookkeeping --
    state.asked_questions.append(reply[:220])
    state.stage_question_count += 1
    state.total_questions += 1
    for topic in _topics_touched(interview, reply):
        if topic not in state.covered_topics:
            state.covered_topics.append(topic)

    interview.state = state
    _save_interview(interview)

    turn = add_turn(
        interview.id,
        speaker=SPEAKER_INTERVIEWER,
        stage=state.stage,
        text=reply,
        meta={"timings": timings.to_dict(), "follow_up": follow_up,
              "effective_difficulty": state.effective_difficulty},
    )

    metrics.record_turn(
        interview_id=interview.id,
        turn_index=turn["turn_index"],
        role_title=interview.role_title,
        timings=timings,
        mode=interview.mode,
    )

    yield {"type": "metrics", "timings": timings.to_dict()}
    yield {
        "type": "done",
        "finished": False,
        "reply": reply,
        "stage": state.stage,
        "turn_index": turn["turn_index"],
        "progress": stage_mod.progress(state, interview.difficulty),
        "timings": timings.to_dict(),
        "effective_difficulty": state.effective_difficulty,
        "follow_up": follow_up,
        "audio_chunks": audio_index,
    }


_THIRD_PERSON_GENERIC_RE = re.compile(
    r"\bthe candidate\b|\b(?:she|he)\s+(?:is|was|has|seems|struggled|didn'?t|did not|lacks?)\b|"
    r"\b(?:her|his)\s+(?:answer|lack|technical|ability|abilities|response|thought process)\b|"
    r"\bleaves? (?:some )?concerns?\b|\bi'?m concerned\b|\bconcerns? about (?:her|his|their)\b",
    re.I,
)


def _is_meta_commentary(sentence: str, first_name: str) -> bool:
    """
    A sentence that talks ABOUT the candidate instead of TO them.

    Small local models sometimes narrate their judgement aloud ("Aisha's lack
    of clarity leaves some concerns about her abilities"), which a real
    interviewer would never say and which pre-empts the scored feedback.
    """
    if _THIRD_PERSON_GENERIC_RE.search(sentence):
        return True
    if first_name and len(first_name) >= 2:
        name = re.escape(first_name)
        # "Aisha's ...", "I think Aisha was ...", "Aisha seems ..." - but not
        # the direct address "Thanks, Aisha." / "Aisha, can you ...".
        if re.search(rf"\b{name}'s\b|\b{name}\s+(?:is|was|has|seems|did|didn'?t|appears|might|may)\b", sentence, re.I):
            return True
    return False


def _closing_line(first_name: str) -> str:
    """Last-resort closing, used only if every sentence the LLM wrote was a question."""
    who = f", {first_name}" if first_name else ""
    return (
        f"Thank you for your time today{who}, that's everything from my side. "
        "We'll be in touch by email about next steps."
    )


def _drop_sentence(sentence: str, first_name: str, *, closing: bool = False) -> bool:
    """Sentences never spoken or stored: third-person judgement, and questions in the closing."""
    if _is_meta_commentary(sentence, first_name):
        return True
    return closing and "?" in sentence


def _clean_reply(reply: str, first_name: str, *, closing: bool = False) -> str:
    """Drop unwanted sentences; keep the reply if nothing would be left."""
    sentences = re.split(r"(?<=[.!?])\s+", reply.strip())
    kept = [s for s in sentences if s and not _drop_sentence(s, first_name, closing=closing)]
    if kept:
        return " ".join(kept).strip()
    return _closing_line(first_name) if closing else reply.strip()


def _speak(text: str, start_index: int, reference: float):
    """Synthesise one sentence; yields (event, elapsed_ms, audio_seconds)."""
    clean = tts.clean_for_speech(text)
    if not clean:
        return
    try:
        started = time.perf_counter()
        result = tts.synthesise(clean)
        elapsed = (time.perf_counter() - started) * 1000
        yield (
            {
                "type": "audio",
                "index": start_index,
                "text": clean,
                "audio_base64": base64.b64encode(result.audio).decode("ascii"),
                "mime": "audio/wav",
                "engine": result.engine,
                "voice": result.voice,
                "audio_seconds": round(result.audio_seconds, 2),
                "synthesis_ms": round(elapsed, 1),
                "since_speech_end_ms": round((time.perf_counter() - reference) * 1000, 1),
            },
            elapsed,
            result.audio_seconds,
        )
    except SpeechError as exc:
        log.warning("TTS failed for a sentence; continuing in text only: %s", exc.message)
        yield ({"type": "tts_error", "message": exc.message, "text": clean}, 0.0, 0.0)


_SENTENCE_ENDINGS = (". ", "! ", "? ", ".\n", "!\n", "?\n")
RUNON_FLUSH_CHARS = 150
_ABBREVIATION_TAILS = (" e.g.", " i.e.", " etc.", " mr.", " mrs.", " dr.", " vs.", " no.")


def _take_complete_sentence(buffer: str) -> tuple[str, str]:
    """
    Split off the first complete sentence from a streaming buffer.

    Returns (sentence, remainder).  Returns ("", buffer) while the buffer holds
    no sentence boundary yet, so the caller just keeps accumulating.
    """
    if len(buffer) < 18:
        return "", buffer

    best = -1
    for ending in _SENTENCE_ENDINGS:
        index = buffer.find(ending)
        while index != -1:
            head = buffer[: index + 1]
            if not any(head.lower().endswith(tail) for tail in _ABBREVIATION_TAILS):
                if best == -1 or index < best:
                    best = index
                break
            index = buffer.find(ending, index + 1)

    if best == -1:
        # A long run-on with no sentence end would hold the audio back for the
        # whole reply, so flush at the last comma instead. 150 characters is
        # roughly ten seconds of speech, which is already too long to wait.
        if len(buffer) > RUNON_FLUSH_CHARS:
            comma = buffer.rfind(", ", 50, RUNON_FLUSH_CHARS)
            if comma > 0:
                return buffer[: comma + 1].strip(), buffer[comma + 1 :]
        return "", buffer

    return buffer[: best + 1].strip(), buffer[best + 1 :]


def _strip_speaker_label(reply: str) -> str:
    """Models occasionally prefix 'Interviewer:' despite being told not to."""
    import re

    out = re.sub(r"^\s*(?:interviewer|you|assistant)\s*:\s*", "", reply, flags=re.I)
    out = re.sub(r"^\s*\*+\s*", "", out)
    return out.strip().strip('"').strip()


def _system_prompt(interview: Interview, state: stage_mod.StageState) -> str:
    spec = stage_mod.spec_for(state.stage)
    plan = interview.plan

    extra: list[str] = [spec.instructions]
    if state.stage == stage_mod.INTRODUCTION and plan.get("opening_line_hint"):
        extra.append(f"Opening guidance: {plan['opening_line_hint']}")
    if state.stage == stage_mod.BACKGROUND and plan.get("cv_talking_points"):
        extra.append("CV points worth probing: " + "; ".join(plan["cv_talking_points"][:5]))
    if state.stage == stage_mod.TECHNICAL:
        remaining = [t for t in plan.get("technical_topics", []) if t not in state.covered_topics]
        extra.append("Technical topics for this role (cover the uncovered ones, hardest last): "
                     + "; ".join((remaining or plan.get("technical_topics", []))[:6]))
        if plan.get("gap_probes"):
            extra.append("Their CV looks light on: " + "; ".join(plan["gap_probes"][:4])
                         + ". Probe one of these without being unkind.")
    if state.stage == stage_mod.BEHAVIOURAL:
        remaining = [t for t in plan.get("behavioural_themes", []) if t not in state.covered_topics]
        extra.append("Behavioural themes: " + "; ".join((remaining or plan.get("behavioural_themes", []))[:5]))

    persona = f"Your persona: {plan['interviewer_persona']}." if plan.get("interviewer_persona") else ""

    return INTERVIEW_SYSTEM_TEMPLATE.format(
        interviewer_name=plan.get("interviewer_name", "Alex Morgan"),
        persona=persona.replace("..", "."),
        role_title=interview.role_title,
        difficulty=state.effective_difficulty,
        difficulty_note=DIFFICULTY_NOTES.get(state.effective_difficulty, DIFFICULTY_NOTES["medium"]),
        stage=spec.name,
        stage_goal=spec.goal,
        stage_question_no=state.stage_question_count + 1,
        stage_question_budget=spec.budget(interview.difficulty),
        stage_instructions="\n".join(extra),
        candidate_context=plan.get("candidate_context", "No CV was provided."),
        role_context=plan.get("role_context", "No structured requirements were available."),
    )


def _uncovered_topics(interview: Interview, state: stage_mod.StageState) -> list[str]:
    plan = interview.plan
    if state.stage == stage_mod.TECHNICAL:
        pool = plan.get("technical_topics", [])
    elif state.stage == stage_mod.BEHAVIOURAL:
        pool = plan.get("behavioural_themes", [])
    elif state.stage == stage_mod.BACKGROUND:
        pool = plan.get("cv_talking_points", [])
    else:
        return []
    return [t for t in pool if t not in state.covered_topics]


def _topics_touched(interview: Interview, reply: str) -> list[str]:
    """Which planned topics this question appears to address."""
    low = reply.lower()
    touched: list[str] = []
    for pool_key in ("technical_topics", "behavioural_themes", "cv_talking_points", "gap_probes"):
        for topic in interview.plan.get(pool_key, []):
            words = [w for w in topic.lower().split() if len(w) > 4]
            if words and sum(1 for w in words if w in low) >= max(1, len(words) // 2):
                touched.append(topic)
    return touched


# ===========================================================================
# Ending
# ===========================================================================


def end_interview(interview_id: str, *, status: str = STATUS_COMPLETE) -> Interview:
    interview = load_interview(interview_id)
    if interview.status == STATUS_ACTIVE:
        interview.status = status if status in (STATUS_COMPLETE, STATUS_ABANDONED) else STATUS_COMPLETE
        interview.ended_at = utcnow()
        if interview.state.stage != stage_mod.COMPLETE:
            interview.state.stage_history.append(
                {"stage": interview.state.stage, "questions": interview.state.stage_question_count,
                 "ended_at": interview.ended_at}
            )
        interview.stage = stage_mod.COMPLETE
        interview.state.stage = stage_mod.COMPLETE
        _save_interview(interview)
        log.info("Interview %s ended with status=%s after %d question(s)",
                 interview.id, interview.status, interview.state.total_questions)
    return interview


def list_interviews(limit: int = 25) -> list[dict[str, Any]]:
    rows = query_all("SELECT * FROM interviews ORDER BY started_at DESC LIMIT ?", (limit,))
    out: list[dict[str, Any]] = []
    for row in rows:
        state = stage_mod.StageState.from_dict(loads(row["state_json"], {}) or {})
        report = loads(row["report_json"], None)
        out.append(
            {
                "id": row["id"],
                "role_title": row["role_title"],
                "difficulty": row["difficulty"],
                "mode": row["mode"],
                "stage": row["stage"],
                "status": row["status"],
                "started_at": row["started_at"],
                "ended_at": row["ended_at"],
                "total_questions": state.total_questions,
                "has_report": bool(report),
                "overall_score": (report or {}).get("overall_score"),
            }
        )
    return out


def save_report(interview_id: str, report: dict[str, Any]) -> None:
    execute("UPDATE interviews SET report_json=? WHERE id=?", (dumps(report), interview_id))


def get_report(interview_id: str) -> dict[str, Any] | None:
    row = query_one("SELECT report_json FROM interviews WHERE id = ?", (interview_id,))
    if row is None:
        raise NotFoundError("That interview could not be found.")
    return loads(row["report_json"], None)
