import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css';

const container = document.getElementById('root');
const boot = document.getElementById('boot');
if (boot) boot.remove();

ReactDOM.createRoot(container as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
