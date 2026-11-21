"""
Skill taxonomy: the curated knowledge base behind skill normalisation.

Why a hand-built taxonomy at all?
---------------------------------
The assignment requires that "React", "ReactJS" and "React.js" be treated as one
skill.  Pure string similarity cannot do this reliably: "React" vs "Redux" are
closer as strings (edit distance 3) than "React" vs "React.js" is to "Reactive
Programming".  A curated alias table gives *exact, explainable* decisions for the
few hundred skills that actually dominate job postings, and the fuzzy / vector
layers in `normalizer.py` then generalise to everything else.

Structure
---------
CANONICAL_SKILLS : canonical name -> metadata
    aliases   : surface forms that mean exactly this skill
    category  : grouping used by the gap dashboard
    implies   : skills this one reasonably demonstrates (React -> JavaScript)

The taxonomy is deliberately data-only so it can be reviewed, extended and
unit-tested without touching algorithm code.
"""

from __future__ import annotations

from typing import Iterable

# Categories used across the UI charts.
CATEGORY_LANGUAGE = "Programming Language"
CATEGORY_FRONTEND = "Frontend"
CATEGORY_BACKEND = "Backend"
CATEGORY_DATABASE = "Database"
CATEGORY_CLOUD = "Cloud & DevOps"
CATEGORY_DATA = "Data & Analytics"
CATEGORY_ML = "Machine Learning & AI"
CATEGORY_SECURITY = "Security"
CATEGORY_TOOL = "Tooling"
CATEGORY_PRACTICE = "Engineering Practice"
CATEGORY_SOFT = "Professional Skill"
CATEGORY_DOMAIN = "Domain Knowledge"
CATEGORY_QUALIFICATION = "Qualification"
CATEGORY_OTHER = "Other"

ALL_CATEGORIES = [
    CATEGORY_LANGUAGE,
    CATEGORY_FRONTEND,
    CATEGORY_BACKEND,
    CATEGORY_DATABASE,
    CATEGORY_CLOUD,
    CATEGORY_DATA,
    CATEGORY_ML,
    CATEGORY_SECURITY,
    CATEGORY_TOOL,
    CATEGORY_PRACTICE,
    CATEGORY_SOFT,
    CATEGORY_DOMAIN,
    CATEGORY_QUALIFICATION,
    CATEGORY_OTHER,
]


def _s(
    aliases: Iterable[str] = (),
    category: str = CATEGORY_OTHER,
    implies: Iterable[str] = (),
) -> dict:
    return {"aliases": list(aliases), "category": category, "implies": list(implies)}


CANONICAL_SKILLS: dict[str, dict] = {
    # ------------------------------------------------------------- languages
    "Python": _s(["python3", "python 3", "py", "cpython"], CATEGORY_LANGUAGE),
    "JavaScript": _s(["js", "ecmascript", "es6", "es2015", "vanilla javascript"], CATEGORY_LANGUAGE),
    "TypeScript": _s(["ts"], CATEGORY_LANGUAGE, ["JavaScript"]),
    "Java": _s(["core java", "java se", "java 8", "java 11", "java 17"], CATEGORY_LANGUAGE),
    "C": _s(["c language", "ansi c", "c programming"], CATEGORY_LANGUAGE),
    "C++": _s(["cpp", "c plus plus", "cplusplus", "c++11", "c++17"], CATEGORY_LANGUAGE),
    "C#": _s(["csharp", "c sharp", "c-sharp"], CATEGORY_LANGUAGE, [".NET"]),
    "Go": _s(["golang", "go lang"], CATEGORY_LANGUAGE),
    "Rust": _s(["rust lang", "rustlang"], CATEGORY_LANGUAGE),
    "PHP": _s(["php7", "php8"], CATEGORY_LANGUAGE),
    "Ruby": _s(["ruby lang"], CATEGORY_LANGUAGE),
    "Swift": _s(["swift lang", "swiftui language"], CATEGORY_LANGUAGE),
    "Kotlin": _s(["kotlin lang"], CATEGORY_LANGUAGE),
    "Scala": _s([], CATEGORY_LANGUAGE),
    "R": _s(["r language", "r programming", "rlang"], CATEGORY_LANGUAGE),
    "MATLAB": _s(["matlab programming"], CATEGORY_LANGUAGE),
    "Bash": _s(["shell scripting", "shell script", "bash scripting", "sh", "zsh", "unix shell"], CATEGORY_LANGUAGE),
    "PowerShell": _s(["power shell", "powershell scripting", "ps1"], CATEGORY_LANGUAGE),
    "SQL": _s(["structured query language", "sql queries", "ansi sql", "writing sql"], CATEGORY_DATABASE),
    "HTML": _s(["html5", "hypertext markup language", "html/css", "semantic html"], CATEGORY_FRONTEND),
    "CSS": _s(["css3", "cascading style sheets"], CATEGORY_FRONTEND),
    "Sass": _s(["scss", "sass", "less", "css preprocessor", "stylus"], CATEGORY_FRONTEND, ["CSS"]),
    "Dart": _s([], CATEGORY_LANGUAGE),
    "Perl": _s([], CATEGORY_LANGUAGE),
    "Assembly": _s(["assembly language", "x86 assembly", "asm"], CATEGORY_LANGUAGE),
    "VBA": _s(["visual basic for applications", "excel vba", "visual basic"], CATEGORY_LANGUAGE),
    "Solidity": _s([], CATEGORY_LANGUAGE),

    # -------------------------------------------------------------- frontend
    "React": _s(
        ["reactjs", "react.js", "react js", "react 18", "react hooks", "reacts"],
        CATEGORY_FRONTEND,
        ["JavaScript"],
    ),
    "Next.js": _s(["nextjs", "next js", "next"], CATEGORY_FRONTEND, ["React", "JavaScript"]),
    "Vue.js": _s(["vue", "vuejs", "vue js", "vue 3", "vue2"], CATEGORY_FRONTEND, ["JavaScript"]),
    "Angular": _s(["angularjs", "angular.js", "angular js", "angular 2+"], CATEGORY_FRONTEND, ["TypeScript"]),
    "Svelte": _s(["sveltekit", "svelte kit"], CATEGORY_FRONTEND, ["JavaScript"]),
    "Redux": _s(["redux toolkit", "react redux", "rtk"], CATEGORY_FRONTEND, ["React"]),
    "Tailwind CSS": _s(["tailwind", "tailwindcss", "tailwind css framework"], CATEGORY_FRONTEND, ["CSS"]),
    "Bootstrap": _s(["bootstrap 5", "bootstrap4"], CATEGORY_FRONTEND, ["CSS"]),
    "Material UI": _s(["mui", "material-ui", "materialui"], CATEGORY_FRONTEND, ["React", "CSS"]),
    "jQuery": _s(["jquery.js", "j query"], CATEGORY_FRONTEND, ["JavaScript"]),
    "Webpack": _s(["web pack"], CATEGORY_TOOL, ["JavaScript"]),
    "Vite": _s(["vitejs", "vite.js"], CATEGORY_TOOL, ["JavaScript"]),
    "Responsive Web Design": _s(["responsive design", "mobile-first design", "responsive layouts"], CATEGORY_FRONTEND, ["CSS"]),
    "Web Accessibility": _s(["accessibility", "a11y", "wcag", "aria"], CATEGORY_FRONTEND),
    "React Native": _s(["reactnative", "react-native"], CATEGORY_FRONTEND, ["React", "JavaScript"]),
    "Flutter": _s([], CATEGORY_FRONTEND, ["Dart"]),

    # --------------------------------------------------------------- backend
    "Node.js": _s(["nodejs", "node js", "node", "node 20"], CATEGORY_BACKEND, ["JavaScript"]),
    "Express.js": _s(["express", "expressjs", "express js"], CATEGORY_BACKEND, ["Node.js"]),
    "NestJS": _s(["nest.js", "nest js"], CATEGORY_BACKEND, ["Node.js", "TypeScript"]),
    "Django": _s(["django rest framework", "drf", "django framework"], CATEGORY_BACKEND, ["Python"]),
    "Flask": _s(["flask framework"], CATEGORY_BACKEND, ["Python"]),
    "FastAPI": _s(["fast api", "fast-api"], CATEGORY_BACKEND, ["Python"]),
    "Spring Boot": _s(["spring", "springboot", "spring framework", "spring mvc"], CATEGORY_BACKEND, ["Java"]),
    ".NET": _s(["dotnet", ".net core", "asp.net", "asp.net core", "dot net", ".net 8"], CATEGORY_BACKEND, ["C#"]),
    "Laravel": _s([], CATEGORY_BACKEND, ["PHP"]),
    "Ruby on Rails": _s(["rails", "rubyonrails", "ror"], CATEGORY_BACKEND, ["Ruby"]),
    "REST API": _s(
        ["rest", "restful api", "restful apis", "rest apis", "api development", "web api", "http api"],
        CATEGORY_BACKEND,
    ),
    "GraphQL": _s(["graph ql", "apollo graphql"], CATEGORY_BACKEND),
    "gRPC": _s(["grpc protocol", "protobuf", "protocol buffers"], CATEGORY_BACKEND),
    "WebSockets": _s(["websocket", "web sockets", "socket.io", "socketio"], CATEGORY_BACKEND),
    "Microservices": _s(["micro services", "microservice architecture", "micro-services"], CATEGORY_PRACTICE),
    "Authentication & Authorization": _s(
        ["oauth", "oauth2", "oauth 2.0", "jwt", "json web tokens", "sso", "openid connect", "auth", "rbac"],
        CATEGORY_SECURITY,
    ),

    # -------------------------------------------------------------- databases
    "PostgreSQL": _s(["postgres", "postgre sql", "psql", "postgresql database"], CATEGORY_DATABASE, ["SQL"]),
    "MySQL": _s(["my sql", "mariadb", "maria db"], CATEGORY_DATABASE, ["SQL"]),
    "SQLite": _s(["sqlite3", "sq lite"], CATEGORY_DATABASE, ["SQL"]),
    "Microsoft SQL Server": _s(["sql server", "mssql", "ms sql", "t-sql", "tsql"], CATEGORY_DATABASE, ["SQL"]),
    "Oracle Database": _s(["oracle", "oracle db", "pl/sql", "plsql"], CATEGORY_DATABASE, ["SQL"]),
    "MongoDB": _s(["mongo", "mongo db", "mongoose"], CATEGORY_DATABASE),
    "Redis": _s(["redis cache"], CATEGORY_DATABASE),
    "Elasticsearch": _s(["elastic search", "elk", "opensearch"], CATEGORY_DATABASE),
    "Cassandra": _s(["apache cassandra"], CATEGORY_DATABASE),
    "DynamoDB": _s(["dynamo db", "aws dynamodb"], CATEGORY_DATABASE, ["AWS"]),
    "Database Design": _s(
        ["data modelling", "data modeling", "schema design", "normalization", "erd", "entity relationship"],
        CATEGORY_DATABASE,
    ),
    "Query Optimisation": _s(
        ["query optimization", "query tuning", "sql tuning", "indexing", "performance tuning sql"],
        CATEGORY_DATABASE,
        ["SQL"],
    ),
    "ORM": _s(["sqlalchemy", "hibernate", "prisma", "entity framework", "object relational mapping"], CATEGORY_DATABASE),

    # -------------------------------------------------------- cloud & devops
    "AWS": _s(
        ["amazon web services", "aws cloud", "ec2", "s3", "aws lambda", "amazon aws", "aws ec2"],
        CATEGORY_CLOUD,
    ),
    "Microsoft Azure": _s(["azure", "ms azure", "azure cloud", "azure devops cloud"], CATEGORY_CLOUD),
    "Google Cloud Platform": _s(["gcp", "google cloud", "bigquery platform"], CATEGORY_CLOUD),
    "Docker": _s(["docker containers", "containerisation", "containerization", "dockerfile"], CATEGORY_CLOUD),
    "Kubernetes": _s(["k8s", "kube", "eks", "aks", "gke", "helm"], CATEGORY_CLOUD, ["Docker"]),
    "CI/CD": _s(
        [
            "ci cd",
            "cicd",
            "continuous integration",
            "continuous delivery",
            "continuous deployment",
            "jenkins",
            "github actions",
            "gitlab ci",
            "circleci",
            "build pipelines",
        ],
        CATEGORY_CLOUD,
    ),
    "Terraform": _s(["infrastructure as code", "iac", "hcl", "terraform cloud"], CATEGORY_CLOUD),
    "Ansible": _s(["configuration management", "ansible playbooks"], CATEGORY_CLOUD),
    "Linux": _s(["linux administration", "unix", "ubuntu", "centos", "rhel", "linux sysadmin"], CATEGORY_CLOUD),
    "Nginx": _s(["nginx web server", "reverse proxy", "apache httpd", "load balancing"], CATEGORY_CLOUD),
    "Monitoring & Observability": _s(
        ["prometheus", "grafana", "datadog", "observability", "splunk monitoring", "new relic", "cloudwatch"],
        CATEGORY_CLOUD,
    ),
    "Serverless": _s(["serverless architecture", "lambda functions", "azure functions", "faas"], CATEGORY_CLOUD),
    "Message Queues": _s(["kafka", "apache kafka", "rabbitmq", "sqs", "pub/sub", "event streaming"], CATEGORY_BACKEND),

    # ------------------------------------------------------ data & analytics
    "Excel": _s(
        ["microsoft excel", "ms excel", "advanced excel", "pivot tables", "excel formulas", "spreadsheets"],
        CATEGORY_DATA,
    ),
    "Power BI": _s(["powerbi", "power-bi", "microsoft power bi", "dax"], CATEGORY_DATA),
    "Tableau": _s(["tableau desktop", "tableau dashboards"], CATEGORY_DATA),
    "Looker": _s(["looker studio", "google data studio", "data studio"], CATEGORY_DATA),
    "Data Visualisation": _s(
        ["data visualization", "dashboarding", "dashboards", "charts and graphs", "visual analytics", "reporting"],
        CATEGORY_DATA,
    ),
    "Pandas": _s(["pandas library", "python pandas", "dataframes"], CATEGORY_DATA, ["Python"]),
    "NumPy": _s(["numpy library", "numerical python"], CATEGORY_DATA, ["Python"]),
    "ETL": _s(
        ["etl pipelines", "elt", "data pipelines", "data ingestion", "airflow", "apache airflow", "dbt", "data engineering"],
        CATEGORY_DATA,
    ),
    "Data Cleaning": _s(
        ["data wrangling", "data preparation", "data preprocessing", "data quality", "data munging"],
        CATEGORY_DATA,
    ),
    "Statistics": _s(
        ["statistical analysis", "descriptive statistics", "inferential statistics", "probability", "statistical methods"],
        CATEGORY_DATA,
    ),
    "A/B Testing": _s(["ab testing", "a b testing", "experimentation", "hypothesis testing", "split testing"], CATEGORY_DATA, ["Statistics"]),
    "Big Data": _s(["hadoop", "spark", "apache spark", "pyspark", "hive", "databricks", "distributed data"], CATEGORY_DATA),
    "Data Warehousing": _s(["snowflake", "redshift", "bigquery", "data warehouse", "star schema", "olap"], CATEGORY_DATA),
    "Business Intelligence": _s(["bi", "bi reporting", "business analytics", "kpi reporting", "mis reporting"], CATEGORY_DATA),
    "Time Series Analysis": _s(["forecasting", "time series forecasting", "arima", "demand forecasting"], CATEGORY_DATA, ["Statistics"]),
    "Google Analytics": _s(["ga4", "google analytics 4", "web analytics"], CATEGORY_DATA),

    # ------------------------------------------------------------- ML and AI
    "Machine Learning": _s(
        ["ml", "machine-learning", "supervised learning", "unsupervised learning", "predictive modelling", "predictive modeling"],
        CATEGORY_ML,
    ),
    "Deep Learning": _s(["neural networks", "dl", "cnn", "rnn", "transformers architecture"], CATEGORY_ML, ["Machine Learning"]),
    "scikit-learn": _s(["sklearn", "scikit learn", "sci-kit learn"], CATEGORY_ML, ["Python", "Machine Learning"]),
    "TensorFlow": _s(["tensor flow", "keras", "tf"], CATEGORY_ML, ["Python", "Deep Learning"]),
    "PyTorch": _s(["torch", "py torch", "pytorch lightning"], CATEGORY_ML, ["Python", "Deep Learning"]),
    "Natural Language Processing": _s(
        ["nlp", "text mining", "text analytics", "spacy", "nltk", "tokenization", "named entity recognition"],
        CATEGORY_ML,
    ),
    "Computer Vision": _s(["cv (vision)", "opencv", "image processing", "object detection"], CATEGORY_ML),
    "Large Language Models": _s(
        ["llm", "llms", "generative ai", "gen ai", "genai", "prompt engineering", "gpt", "openai api", "rag",
         "retrieval augmented generation", "langchain", "fine-tuning"],
        CATEGORY_ML,
    ),
    "MLOps": _s(["ml ops", "model deployment", "mlflow", "model monitoring", "feature store"], CATEGORY_ML, ["Machine Learning"]),
    "Speech Recognition": _s(["asr", "automatic speech recognition", "whisper", "speech to text", "stt"], CATEGORY_ML),
    "Text-to-Speech": _s(["tts", "speech synthesis", "voice synthesis"], CATEGORY_ML),
    "Recommendation Systems": _s(["recommender systems", "collaborative filtering"], CATEGORY_ML, ["Machine Learning"]),
    "Feature Engineering": _s(["feature selection", "feature extraction"], CATEGORY_ML, ["Machine Learning"]),
    "Model Evaluation": _s(
        ["cross validation", "cross-validation", "precision recall", "roc auc", "confusion matrix", "model validation"],
        CATEGORY_ML,
        ["Machine Learning"],
    ),

    # --------------------------------------------------------------- security
    "Network Security": _s(
        ["firewalls", "firewall", "ids", "ips", "intrusion detection", "intrusion prevention", "vpn", "network defence", "network defense"],
        CATEGORY_SECURITY,
    ),
    "SIEM": _s(["splunk", "qradar", "arcsight", "microsoft sentinel", "azure sentinel", "log analysis", "elastic siem"], CATEGORY_SECURITY),
    "Incident Response": _s(
        ["incident handling", "ir", "soc operations", "security operations centre", "security operations center",
         "triage", "incident management", "blue team"],
        CATEGORY_SECURITY,
    ),
    "Vulnerability Management": _s(
        ["vulnerability assessment", "vulnerability scanning", "nessus", "qualys", "openvas", "patch management", "cve analysis"],
        CATEGORY_SECURITY,
    ),
    "Penetration Testing": _s(
        ["pen testing", "pentest", "pentesting", "ethical hacking", "red team", "metasploit", "burp suite", "offensive security"],
        CATEGORY_SECURITY,
    ),
    "Malware Analysis": _s(["reverse engineering malware", "static analysis", "dynamic analysis", "sandboxing"], CATEGORY_SECURITY),
    "Digital Forensics": _s(["computer forensics", "forensic analysis", "memory forensics", "autopsy", "ftk"], CATEGORY_SECURITY),
    "Threat Intelligence": _s(["cti", "threat hunting", "ioc analysis", "mitre attack", "mitre att&ck", "attack framework"], CATEGORY_SECURITY),
    "Cryptography": _s(["encryption", "pki", "tls", "ssl", "hashing", "key management"], CATEGORY_SECURITY),
    "Security Compliance": _s(
        ["iso 27001", "iso27001", "nist", "nist csf", "gdpr", "hipaa", "pci dss", "soc 2", "compliance frameworks", "risk assessment"],
        CATEGORY_SECURITY,
    ),
    "Identity & Access Management": _s(["iam", "active directory", "ldap", "privileged access management", "pam", "okta"], CATEGORY_SECURITY),
    "Cloud Security": _s(["cspm", "aws security", "azure security", "cloud hardening", "security groups"], CATEGORY_SECURITY, ["AWS"]),
    "Endpoint Security": _s(["edr", "xdr", "antivirus", "crowdstrike", "defender for endpoint", "host-based security"], CATEGORY_SECURITY),
    "Packet Analysis": _s(["wireshark", "tcpdump", "network traffic analysis", "pcap analysis"], CATEGORY_SECURITY),
    "Networking": _s(
        ["tcp/ip", "tcp ip", "dns", "dhcp", "osi model", "routing and switching", "subnetting", "network protocols", "network fundamentals"],
        CATEGORY_SECURITY,
    ),
    "Secure Coding": _s(["owasp", "owasp top 10", "application security", "appsec", "sast", "dast", "code review security"], CATEGORY_SECURITY),

    # ---------------------------------------------------------------- tooling
    "Git": _s(["git version control", "github", "gitlab", "bitbucket", "version control", "git flow"], CATEGORY_TOOL),
    "Jira": _s(["atlassian jira", "jira software", "confluence"], CATEGORY_TOOL),
    "Postman": _s(["postman api", "insomnia", "api testing tool"], CATEGORY_TOOL),
    "Figma": _s(["figma design", "adobe xd", "sketch app"], CATEGORY_TOOL),
    "Adobe Photoshop": _s(["photoshop", "adobe ps"], CATEGORY_TOOL),
    "VS Code": _s(["visual studio code", "vscode"], CATEGORY_TOOL),
    "Jupyter": _s(["jupyter notebook", "jupyter notebooks", "google colab", "colab"], CATEGORY_TOOL, ["Python"]),

    # ---------------------------------------------------- engineering practice
    "Unit Testing": _s(
        ["pytest", "jest", "junit", "unit tests", "test driven development", "tdd", "mocha", "vitest"],
        CATEGORY_PRACTICE,
    ),
    "Integration Testing": _s(["end to end testing", "e2e testing", "selenium", "cypress", "playwright", "automated testing"], CATEGORY_PRACTICE),
    "Agile": _s(["agile methodology", "scrum", "kanban", "sprint planning", "agile development", "safe agile"], CATEGORY_PRACTICE),
    "Code Review": _s(["peer review", "pull requests", "pr review", "merge requests"], CATEGORY_PRACTICE, ["Git"]),
    "System Design": _s(
        ["software architecture", "architecture design", "scalable systems", "distributed systems", "high level design", "design patterns"],
        CATEGORY_PRACTICE,
    ),
    "Data Structures & Algorithms": _s(
        ["dsa", "data structures", "algorithms", "algorithm design", "complexity analysis", "coding problems", "leetcode"],
        CATEGORY_PRACTICE,
    ),
    "Object-Oriented Programming": _s(["oop", "object oriented design", "ood", "solid principles"], CATEGORY_PRACTICE),
    "Debugging": _s(["troubleshooting", "root cause analysis", "fault diagnosis"], CATEGORY_PRACTICE),
    "Documentation": _s(["technical writing", "technical documentation", "writing docs", "api documentation"], CATEGORY_PRACTICE),
    "Performance Optimisation": _s(["performance optimization", "profiling", "caching strategies", "latency optimisation"], CATEGORY_PRACTICE),

    # ------------------------------------------------------ professional skills
    "Communication": _s(
        ["communication skills", "verbal communication", "written communication", "interpersonal skills",
         "excellent communicator", "clear communication"],
        CATEGORY_SOFT,
    ),
    "Teamwork": _s(["collaboration", "team player", "cross-functional collaboration", "working in teams"], CATEGORY_SOFT),
    "Problem Solving": _s(["analytical thinking", "critical thinking", "analytical skills", "problem-solving skills"], CATEGORY_SOFT),
    "Stakeholder Management": _s(
        ["stakeholder communication", "client management", "business partnering", "requirements gathering"],
        CATEGORY_SOFT,
    ),
    "Leadership": _s(["team leadership", "mentoring", "people management", "leading teams", "mentorship"], CATEGORY_SOFT),
    "Time Management": _s(["prioritisation", "prioritization", "organisational skills", "organizational skills", "meeting deadlines"], CATEGORY_SOFT),
    "Attention to Detail": _s(["detail oriented", "detail-oriented", "accuracy", "meticulous"], CATEGORY_SOFT),
    "Presentation Skills": _s(["presenting", "public speaking", "storytelling with data", "data storytelling"], CATEGORY_SOFT),
    "Adaptability": _s(["flexibility", "learning agility", "fast learner", "willingness to learn"], CATEGORY_SOFT),
    "Project Management": _s(["pmp", "project planning", "project delivery", "programme management"], CATEGORY_SOFT),
    "Customer Focus": _s(["customer service", "client facing", "customer success", "user empathy"], CATEGORY_SOFT),

    # ------------------------------------------------------- domain knowledge
    "Business Acumen": _s(["business understanding", "commercial awareness", "domain knowledge", "business domain"], CATEGORY_DOMAIN),
    "Financial Analysis": _s(["finance", "financial modelling", "financial modeling", "budgeting", "p&l"], CATEGORY_DOMAIN),
    "Healthcare Domain": _s(["clinical data", "ehr", "hl7", "fhir", "medical records"], CATEGORY_DOMAIN),
    "E-commerce Domain": _s(["retail analytics", "marketplace", "online retail"], CATEGORY_DOMAIN),
    "Marketing Analytics": _s(["campaign analysis", "seo", "digital marketing", "attribution modelling"], CATEGORY_DOMAIN),
    "Product Management": _s(["product ownership", "roadmapping", "product strategy", "user stories"], CATEGORY_DOMAIN),
    "UX Research": _s(["user research", "usability testing", "user interviews", "ux design"], CATEGORY_DOMAIN),

    # --------------------------------------------------------- qualifications
    "Bachelor's Degree": _s(
        ["bachelors degree", "bs degree", "bsc", "b.sc", "be degree", "b.e", "undergraduate degree",
         "bachelor of science", "bs computer science", "bachelors"],
        CATEGORY_QUALIFICATION,
    ),
    "Master's Degree": _s(["masters degree", "ms degree", "msc", "m.sc", "mba", "postgraduate degree", "masters"], CATEGORY_QUALIFICATION),
    "PhD": _s(["doctorate", "ph.d", "doctoral degree"], CATEGORY_QUALIFICATION),
    "CompTIA Security+": _s(["security plus", "sec+", "comptia security plus", "securityplus"], CATEGORY_QUALIFICATION),
    "CompTIA Network+": _s(["network plus", "net+", "comptia network plus"], CATEGORY_QUALIFICATION),
    "CISSP": _s(["certified information systems security professional"], CATEGORY_QUALIFICATION),
    "CEH": _s(["certified ethical hacker"], CATEGORY_QUALIFICATION),
    "AWS Certification": _s(
        ["aws certified", "aws solutions architect", "aws certified developer", "aws cloud practitioner"],
        CATEGORY_QUALIFICATION,
        ["AWS"],
    ),
    "Azure Certification": _s(["az-900", "azure certified", "azure administrator associate"], CATEGORY_QUALIFICATION, ["Microsoft Azure"]),
    "Google Data Analytics Certificate": _s(["google data analytics", "coursera data analytics certificate"], CATEGORY_QUALIFICATION),
    "Scrum Certification": _s(["csm", "psm", "certified scrum master", "professional scrum master"], CATEGORY_QUALIFICATION, ["Agile"]),
}


# ---------------------------------------------------------------------------
# Derived lookup tables (built once at import time)
# ---------------------------------------------------------------------------

def _build_alias_index() -> dict[str, str]:
    """
    normalised alias/canonical string -> canonical skill name.

    Each name is indexed under its *conservative* key (noise words kept).  The
    aggressive key -- the one a user's messy input produces -- is only added
    when normalisation dropped nothing, because a lossy aggressive key is
    dangerously generic:

        "security plus"    -> "security"   would match every security advert
        "domain knowledge" -> "domain"     would match almost anything

    Indexing the conservative form keeps those aliases usable (the document
    scanner searches full text, where "security plus" appears verbatim) while
    the lossless aggressive keys still let "Experience with ReactJS (3+ years)"
    resolve to React.
    """
    from app.services.skills.text_norm import normalise_key  # local import avoids cycle

    index: dict[str, str] = {}

    def add(name: str, canonical: str) -> None:
        conservative = normalise_key(name, strip_noise=False)
        if conservative and conservative not in index:
            index[conservative] = canonical

        aggressive = normalise_key(name)
        if not aggressive or aggressive in index:
            return
        # Only register the aggressive key when it kept every word.
        if len(aggressive.split()) == len(conservative.split()):
            index[aggressive] = canonical

    for canonical, meta in CANONICAL_SKILLS.items():
        add(canonical, canonical)
        for alias in meta["aliases"]:
            add(alias, canonical)
    return index


ALIAS_INDEX: dict[str, str] = _build_alias_index()
CANONICAL_NAMES: list[str] = sorted(CANONICAL_SKILLS)

# Minimum key length for scanning a whole DOCUMENT for a skill.  Short keys
# such as "r", "go", "ml" or "dl" are real skills but also ordinary English
# words/fragments, so matching them inside prose produces far more false
# positives than true ones.  They still resolve fine when a user lists them
# explicitly as a skill, which goes through the exact alias lookup instead.
DOCUMENT_SCAN_MIN_KEY_LENGTH = 3


def category_of(canonical: str) -> str:
    meta = CANONICAL_SKILLS.get(canonical)
    return meta["category"] if meta else CATEGORY_OTHER


def implied_by(canonical: str) -> list[str]:
    """Skills that holding `canonical` reasonably demonstrates."""
    meta = CANONICAL_SKILLS.get(canonical)
    return list(meta["implies"]) if meta else []


def taxonomy_stats() -> dict[str, int]:
    return {
        "canonical_skills": len(CANONICAL_SKILLS),
        "alias_entries": len(ALIAS_INDEX),
        "categories": len(ALL_CATEGORIES),
        "implication_edges": sum(len(m["implies"]) for m in CANONICAL_SKILLS.values()),
    }
