import React, { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { useToast } from '@/hooks/use-toast';
import { Facebook, AlertTriangle } from 'lucide-react';

/* Decorative card suits in background */
const BackgroundSuits = () => (
  <div className="absolute inset-0 overflow-hidden pointer-events-none select-none">
    {[
      { suit: '♠', x: '8%',  y: '12%', size: '5rem', rotate: '-15deg', opacity: 0.06 },
      { suit: '♥', x: '85%', y: '8%',  size: '6rem', rotate: '20deg',  opacity: 0.06 },
      { suit: '♦', x: '5%',  y: '72%', size: '4rem', rotate: '-8deg',  opacity: 0.05 },
      { suit: '♣', x: '88%', y: '68%', size: '5.5rem',rotate: '12deg', opacity: 0.05 },
      { suit: '♥', x: '50%', y: '5%',  size: '3.5rem',rotate: '0deg',  opacity: 0.04 },
      { suit: '♠', x: '92%', y: '38%', size: '4rem', rotate: '25deg',  opacity: 0.04 },
      { suit: '♦', x: '2%',  y: '42%', size: '3rem', rotate: '-20deg', opacity: 0.04 },
    ].map((s, i) => (
      <span
        key={i}
        className="absolute font-bold text-white"
        style={{ left: s.x, top: s.y, fontSize: s.size, transform: `rotate(${s.rotate})`, opacity: s.opacity }}
      >
        {s.suit}
      </span>
    ))}
    {[
      { left: '-40px', top: '20%',  rotate: '-25deg' },
      { right: '-40px', top: '30%', rotate: '20deg'  },
      { left: '5%', bottom: '10%',  rotate: '-10deg' },
      { right: '5%', bottom: '15%', rotate: '15deg'  },
    ].map((pos, i) => (
      <div
        key={i}
        className="absolute w-16 h-24 rounded-lg bg-white/5 border border-white/10"
        style={{ ...pos } as React.CSSProperties}
      />
    ))}
  </div>
);

const Login = () => {
  const { login, loginAsGuest, loading, configured } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const { toast } = useToast();
  const [loadingProvider, setLoadingProvider] = useState<'facebook' | 'google' | null>(null);

  const from = location.state?.from?.pathname || '/lobby';

  const handleLogin = async (provider: 'facebook' | 'google') => {
    setLoadingProvider(provider);
    try {
      await login(provider);
      toast({ title: 'Welcome back!', description: 'Redirecting to lobby…' });
      navigate(from, { replace: true });
    } catch {
      toast({ title: 'Login failed', description: 'Please try again.', variant: 'destructive' });
    } finally {
      setLoadingProvider(null);
    }
  };

  return (
    <div
      className="min-h-screen flex items-center justify-center relative overflow-hidden"
      style={{ background: 'radial-gradient(ellipse at 50% 40%, #1a0d3a 0%, #0a0618 60%, #000 100%)' }}
    >
      <BackgroundSuits />

      {/* Gold top line */}
      <div
        className="absolute top-0 left-0 right-0 h-1"
        style={{ background: 'linear-gradient(90deg, transparent, #d4af37, #f0d060, #d4af37, transparent)' }}
      />

      <div className="relative z-10 w-full max-w-md px-4">
        {/* Logo / brand */}
        <div className="text-center mb-8 fade-in-up">
          <div className="flex justify-center mb-5">
            <div className="relative" style={{ width: 72, height: 80 }}>
              {[{ suit: '♠', color: '#1a1a2e', rotate: '-18deg', left: 0 }, { suit: '♥', color: '#dc2626', rotate: '12deg', left: 26 }].map((c, i) => (
                <div
                  key={i}
                  className="absolute w-14 h-20 rounded-xl bg-white shadow-2xl flex items-start p-1.5"
                  style={{ top: 0, left: c.left, transform: `rotate(${c.rotate})`, zIndex: i + 1, boxShadow: '0 8px 24px rgba(0,0,0,0.5)' }}
                >
                  <span className="font-black text-xl leading-none" style={{ color: c.color }}>{c.suit}</span>
                </div>
              ))}
            </div>
          </div>

          <h1 className="text-4xl font-black tracking-wider mb-1" style={{ fontFamily: 'Georgia, serif' }}>
            <span className="gold-text">TEEN PATTI</span>
          </h1>
          <p className="text-yellow-500/60 tracking-[0.35em] uppercase text-xs font-semibold">Playroom</p>
        </div>

        {/* Login card */}
        <div
          className="rounded-2xl p-8 scale-in"
          style={{
            background: 'linear-gradient(135deg, rgba(255,255,255,0.06) 0%, rgba(255,255,255,0.02) 100%)',
            border: '1px solid rgba(212,175,55,0.25)',
            boxShadow: '0 25px 80px rgba(0,0,0,0.6), inset 0 1px 0 rgba(212,175,55,0.12)',
            backdropFilter: 'blur(20px)',
          }}
        >
          <h2 className="text-white text-center text-xl font-bold mb-1">Sign In to Play</h2>
          <p className="text-white/40 text-center text-sm mb-6">Join thousands of players at the table</p>

          {/* Not-configured warning */}
          {!configured && (
            <div className="flex items-start gap-2 rounded-xl px-4 py-3 mb-6" style={{ background: 'rgba(234,179,8,0.1)', border: '1px solid rgba(234,179,8,0.3)' }}>
              <AlertTriangle size={16} className="text-yellow-400 flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-yellow-300 font-semibold text-xs">OAuth not configured</p>
                <p className="text-yellow-400/70 text-xs mt-0.5">
                  Follow <span className="font-mono font-bold">AUTH_SETUP.md</span> to connect real Facebook &amp; Google login. Login is disabled until Firebase env vars are set.
                </p>
              </div>
            </div>
          )}

          {/* Facebook Login — Primary CTA */}
          <button
            onClick={() => handleLogin('facebook')}
            disabled={loading || loadingProvider !== null || !configured}
            className="w-full flex items-center justify-center gap-3 py-4 px-6 rounded-xl font-bold text-white text-base mb-4 transition-all duration-200 active:scale-95 disabled:opacity-60 disabled:cursor-not-allowed"
            style={{
              background: 'linear-gradient(135deg, #1877f2 0%, #0e5fcd 100%)',
              boxShadow: '0 4px 20px rgba(24,119,242,0.45), inset 0 1px 0 rgba(255,255,255,0.15)',
            }}
          >
            {loadingProvider === 'facebook' ? (
              <>
                <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                <span>Connecting…</span>
              </>
            ) : (
              <>
                <div className="w-8 h-8 bg-white rounded-full flex items-center justify-center flex-shrink-0">
                  <Facebook size={20} className="text-[#1877f2]" fill="#1877f2" />
                </div>
                <span>Continue with Facebook</span>
              </>
            )}
          </button>

          {/* Divider */}
          <div className="flex items-center gap-3 my-5">
            <div className="flex-1 h-px bg-white/10" />
            <span className="text-white/30 text-xs">or</span>
            <div className="flex-1 h-px bg-white/10" />
          </div>

          {/* Google Login — Secondary */}
          <button
            onClick={() => handleLogin('google')}
            disabled={loading || loadingProvider !== null || !configured}
            className="w-full flex items-center justify-center gap-3 py-3 px-6 rounded-xl font-semibold text-white/75 text-sm mb-7 transition-all duration-200 active:scale-95 disabled:opacity-60 hover:bg-white/10 disabled:cursor-not-allowed"
            style={{ background: 'rgba(255,255,255,0.07)', border: '1px solid rgba(255,255,255,0.12)' }}
          >
            {loadingProvider === 'google' ? (
              <>
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                <span>Connecting…</span>
              </>
            ) : (
              <>
                <svg width="18" height="18" viewBox="0 0 18 18">
                  <path d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908c1.702-1.567 2.684-3.875 2.684-6.615z" fill="#4285F4"/>
                  <path d="M9 18c2.43 0 4.467-.806 5.956-2.184l-2.908-2.258c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332C2.438 15.983 5.482 18 9 18z" fill="#34A853"/>
                  <path d="M3.964 10.707c-.18-.54-.282-1.117-.282-1.707s.102-1.167.282-1.707V4.961H.957C.347 6.175 0 7.55 0 9s.348 2.825.957 4.039l3.007-2.332z" fill="#FBBC05"/>
                  <path d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0 5.482 0 2.438 2.017.957 4.961L3.964 7.293C4.672 5.167 6.656 3.58 9 3.58z" fill="#EA4335"/>
                </svg>
                <span>Continue with Google</span>
              </>
            )}
          </button>

          {/* DEV BYPASS — delete this button block when real OAuth is live */}
          <button
            onClick={() => { loginAsGuest(); navigate(from, { replace: true }); }}
            className="w-full py-2.5 rounded-xl text-xs font-semibold mb-5 transition-all active:scale-95"
            style={{ background: 'rgba(255,255,255,0.04)', border: '1px dashed rgba(255,255,255,0.15)', color: 'rgba(255,255,255,0.35)' }}
          >
            ⚡ Skip Login — Demo Mode
          </button>

          <p className="text-center text-white/25 text-xs leading-relaxed">
            By signing in you agree to our Terms of Service.<br />
            Play responsibly. 18+ only.
          </p>
        </div>

        {/* Feature chips */}
        <div className="flex justify-center gap-3 mt-6 flex-wrap">
          {['Free Chips Daily', 'Live Tournaments', 'Secure & Fair'].map(f => (
            <div
              key={f}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium text-yellow-400/60"
              style={{ border: '1px solid rgba(212,175,55,0.2)', background: 'rgba(212,175,55,0.04)' }}
            >
              <span className="w-1.5 h-1.5 rounded-full bg-yellow-500/50 flex-shrink-0" />
              {f}
            </div>
          ))}
        </div>
      </div>

      <div
        className="absolute bottom-0 left-0 right-0 h-px"
        style={{ background: 'linear-gradient(90deg, transparent, #d4af37, transparent)' }}
      />
    </div>
  );
};

export default Login;
