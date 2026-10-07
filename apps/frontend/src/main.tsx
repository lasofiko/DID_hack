import { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';

function App() {
  const [status, setStatus] = useState('Проверка подключения…');

  useEffect(() => {
    fetch('/api/health')
      .then(response => {
        if (!response.ok) throw new Error('API unavailable');
        return response.json();
      })
      .then(() => setStatus('Бэкенд подключён'))
      .catch(() => setStatus('Бэкенд недоступен'));
  }, []);

  return <main>
    <h1>DID Hack</h1>
    <p>Здесь будет интерфейс управления роботом.</p>
    <p role="status">{status}</p>
  </main>;
}

createRoot(document.getElementById('root')!).render(<App />);
