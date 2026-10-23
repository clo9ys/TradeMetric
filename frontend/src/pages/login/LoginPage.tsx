import { useState } from 'react';
import type { FormEvent } from 'react';
import './LoginPage.css';

export function LoginPage() {
  const [message, setMessage] = useState('');

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage('Вход станет доступен после подключения сервера авторизации.');
  }

  return <main className="login-page">
    <section className="login-introduction" aria-labelledby="product-name">
      <div className="login-brand"><h1 id="product-name">TradeMetric</h1><p>Модуль расчёта риск-метрик</p></div>
      <p className="login-description">Профессиональный<br className="desktop-break" /> инструмент для оценки<br className="desktop-break" /> рыночных рисков торговой<br className="desktop-break" /> книги. Моделируйте<br className="desktop-break" /> гипотетические сделки и<br className="desktop-break" /> анализируйте их влияние<br className="desktop-break" /> на общий портфель<br className="desktop-break" /> ценных бумаг.</p>
    </section>
    <section className="login-card" aria-labelledby="login-heading">
      <h2 id="login-heading">Вход в аккаунт</h2>
      <form onSubmit={submit}>
        <label className="sr-only" htmlFor="login">Логин</label>
        <input id="login" name="username" autoComplete="username" placeholder="Логин" required onChange={() => setMessage('')} />
        <label className="sr-only" htmlFor="password">Пароль</label>
        <input id="password" name="password" type="password" autoComplete="current-password" placeholder="Пароль" required onChange={() => setMessage('')} />
        <button className="button button-primary" type="submit">Войти</button>
        {message && <p className="status-message" role="status">{message}</p>}
      </form>
    </section>
    <p className="login-summary">Принимайте обоснованные торговые решения на основе мгновенного<br className="desktop-break" /> вычисления показателя DV01 и справедливой стоимости.<br className="desktop-break" /> Платформа позволяет оценивать чувствительность портфеля к<br className="desktop-break" /> колебаниям процентных ставок с точностью до базисного пункта.</p>
  </main>;
}
