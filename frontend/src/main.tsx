import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';

import { Layout } from './components/Layout';
import { AppProvider } from './lib/store';
import CVAnalysis from './pages/CVAnalysis';
import Dashboard from './pages/Dashboard';
import Improve from './pages/Improve';
import Interview from './pages/Interview';
import Performance from './pages/Performance';
import Results from './pages/Results';
import RoleAnalysis from './pages/RoleAnalysis';
import SettingsPage from './pages/Settings';
import SkillGap from './pages/SkillGap';
import './index.css';

const root = document.getElementById('root');
if (!root) throw new Error('Root element #root was not found in index.html');

createRoot(root).render(
  <StrictMode>
    <BrowserRouter>
      <AppProvider>
        <Layout>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/cv" element={<CVAnalysis />} />
            <Route path="/cv/:cvId" element={<CVAnalysis />} />
            <Route path="/roles" element={<RoleAnalysis />} />
            <Route path="/roles/:roleId" element={<RoleAnalysis />} />
            <Route path="/gap" element={<SkillGap />} />
            <Route path="/gap/:gapId" element={<SkillGap />} />
            <Route path="/improve" element={<Improve />} />
            <Route path="/interview" element={<Interview />} />
            <Route path="/interview/:interviewId" element={<Interview />} />
            <Route path="/results" element={<Results />} />
            <Route path="/results/:interviewId" element={<Results />} />
            <Route path="/performance" element={<Performance />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Layout>
      </AppProvider>
    </BrowserRouter>
  </StrictMode>,
);
