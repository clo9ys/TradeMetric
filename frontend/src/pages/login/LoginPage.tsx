import { useState } from 'react';
import type { FormEvent } from 'react';
import { login as loginRequest } from '../../api/auth';
import type { CurrentUser } from '../../api/auth';
import { ApiError } from '../../api/client';
import './LoginPage.css';

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

interface Props { onLoggedIn: (user: CurrentUser) => void }

export function LoginPage({ onLoggedIn }: Props) {
  const [message, setMessage] = useState('');
  const [errors, setErrors] = useState({ login: '', password: '' });
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const login = form.elements.namedItem('username') as HTMLInputElement;
    const password = form.elements.namedItem('password') as HTMLInputElement;
    const email = login.value.trim();
    const next = {
      login: !email ? 'Введите email' : !EMAIL_PATTERN.test(email) ? 'Введите email в формате name@example.com' : '',
      password: password.value ? '' : 'Введите пароль',
    };
    setErrors(next);
    setMessage('');
    if (next.login || next.password) {
      (next.login ? login : password).focus();
      return;
    }
    setSubmitting(true);
    try {
      onLoggedIn(await loginRequest(email, password.value));
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : 'Не удалось войти. Попробуйте ещё раз.');
      password.select();
    } finally {
      setSubmitting(false);
    }
  }

  return <main className="login-page">
    <section className="login-introduction" aria-labelledby="product-name">
      <div className="login-brand"><h1 id="product-name">TradeMetric</h1><p>Модуль расчёта риск-метрик</p></div>
      <p className="login-description">Профессиональный<br className="desktop-break" /> инструмент для оценки<br className="desktop-break" /> рыночных рисков торговой<br className="desktop-break" /> книги. Моделируйте<br className="desktop-break" /> гипотетические сделки и<br className="desktop-break" /> анализируйте их влияние<br className="desktop-break" /> на общий портфель<br className="desktop-break" /> ценных бумаг.</p>
    </section>
    <section className="login-card" aria-labelledby="login-heading">
      <h2 id="login-heading">Вход в аккаунт</h2>
      <form onSubmit={submit} noValidate>
        <div className="login-field">
        <label className="sr-only" htmlFor="login">Email</label>
        <input id="login" name="username" type="email" inputMode="email" autoComplete="username" placeholder="Email" required aria-invalid={Boolean(errors.login)} aria-describedby={errors.login ? 'login-error' : undefined} onChange={event => { setMessage(''); if (event.target.value .trim()) setErrors(previous => ({ ...previous, login: '' })); }} />
        {errors.login && <p id="login-error" className="login-field-error" role="alert">{errors.login}</p>}
        </div>
        <div className="login-field">
        <label className="sr-only" htmlFor="password">Пароль</label>
        <input id="password" name="password" type="password" autoComplete="current-password" placeholder="Пароль" required aria-invalid={Boolean(errors.password)} aria-describedby={errors.password ? 'password-error' : undefined} onChange={event => { setMessage(''); if (event.target.value) setErrors(previous => ({ ...previous, password: '' })); }} />
        {errors.password && <p id="password-error" className="login-field-error" role="alert">{errors.password}</p>}
        </div>
        <button className="button button-primary" type="submit" disabled={submitting}>{submitting ? 'Входим…' : 'Войти'}</button>
        {message && <p className="status-message status-error" role="alert">{message}</p>}
      </form>
    </section>
    <p className="login-summary">Принимайте обоснованные торговые решения на основе мгновенного<br className="desktop-break" /> вычисления показателя DV01 и справедливой стоимости.<br className="desktop-break" /> Платформа позволяет оценивать чувствительность портфеля к<br className="desktop-break" /> колебаниям процентных ставок с точностью до базисного пункта.</p>
  </main>;
}
