import { beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import Login from './Login.vue';

vi.mock('axios', () => ({ default: { post: vi.fn() } }));

beforeEach(() => vi.clearAllMocks());

function loginContext() {
  const context = {
    ...Login.data(),
    email: 'captain',
    password: 'secret',
    $store: { dispatch: vi.fn().mockResolvedValue(true) },
    $router: { push: vi.fn().mockResolvedValue() },
  };
  context.completeLogin = () => Login.methods.completeLogin.call(context);
  return context;
}

describe('cookie login', () => {
  it('uses the authenticated cookie after a successful password login', async () => {
    const context = loginContext();
    axios.post.mockResolvedValueOnce({ data: { login: 'successful' } });

    await Login.methods.login.call(context);

    expect(axios.post).toHaveBeenCalledTimes(1);
    expect(context.$store.dispatch).toHaveBeenCalledWith('auth/AUTH_CHECK');
    expect(context.$router.push).toHaveBeenCalledWith('/');
  });

  it('passes the OTP once and does not repeat password login without it', async () => {
    const context = loginContext();
    axios.post.mockResolvedValueOnce({ data: { login: '2fa_required' } });
    await Login.methods.login.call(context);
    expect(context.requires2FA).toBe(true);

    context.otpToken = '123456';
    axios.post.mockResolvedValueOnce({ data: { login: 'successful' } });
    await Login.methods.verify2FA.call(context);

    expect(axios.post).toHaveBeenCalledTimes(2);
    expect(axios.post).toHaveBeenLastCalledWith(
      '/auth/login_cookie',
      { username: 'captain', password: 'secret', otp_token: '123456' },
      { withCredentials: true },
    );
    expect(context.$store.dispatch).toHaveBeenCalledTimes(1);
    expect(context.$router.push).toHaveBeenCalledWith('/');
  });
});
