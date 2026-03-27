import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';

const Index = () => {
  const navigate = useNavigate();
  const { user } = useAuth();

  const handlePlay = () => navigate(user ? '/lobby' : '/login');

  return (
    <div
      className="min-h-screen flex flex-col items-center justify-center relative overflow-hidden"
      style={{ background: 'radial-gradient(ellipse at 50% 40%, #1a0d3a 0%, #0a0618 60%, #000 100%)' }}
    >
      <div className="absolute top-0 left-0 right-0 h-1" style={{ background: 'linear-gradient(90deg, transparent, #d4af37, #f0d060, #d4af37, transparent)' }} />
      <div className="absolute bottom-0 left-0 right-0 h-px" style={{ background: 'linear-gradient(90deg, transparent, #d4af37, transparent)' }} />

      {/* Floating suit icons */}
      {[
        { s: '♠', x: '6%',  y: '15%', sz: '5rem', r: '-18deg', o: 0.06 },
        { s: '♥', x: '88%', y: '10%', sz: '6rem', r: '22deg',  o: 0.06 },
        { s: '♦', x: '4%',  y: '70%', sz: '4rem', r: '-8deg',  o: 0.05 },
        { s: '♣', x: '90%', y: '65%', sz: '5rem', r: '14deg',  o: 0.05 },
        { s: '♥', x: '48%', y: '4%',  sz: '3.5rem',r: '0deg',  o: 0.04 },
        { s: '♠', x: '93%', y: '40%', sz: '3.5rem',r: '28deg', o: 0.04 },
        { s: '♦', x: '1%',  y: '44%', sz: '3rem', r: '-22deg', o: 0.04 },
      ].map((s, i) => (
        <span key={i} className="absolute font-bold text-white pointer-events-none select-none"
          style={{ left: s.x, top: s.y, fontSize: s.sz, transform: `rotate(${s.r})`, opacity: s.o }}
        >{s.s}</span>
      ))}

      <div className="relative z-10 text-center px-6 max-w-2xl fade-in-up">
        {/* Decorative card fan */}
        <div className="flex justify-center mb-8 relative" style={{ height: 100 }}>
          {[
            { suit: '♠', color: '#1a1a2e', rotate: '-20deg', left: '33%' },
            { suit: '♥', color: '#dc2626', rotate: '0deg',   left: '42%' },
            { suit: '♦', color: '#dc2626', rotate: '18deg',  left: '51%' },
          ].map((c, i) => (
            <div
              key={i}
              className="absolute rounded-xl bg-white flex items-start p-2"
              style={{ width: 60, height: 84, left: c.left, top: 0, transform: `rotate(${c.rotate})`, zIndex: i + 1, boxShadow: '0 12px 32px rgba(0,0,0,0.6)' }}
            >
              <span className="font-black text-2xl leading-none" style={{ color: c.color }}>{c.suit}</span>
            </div>
          ))}
        </div>

        <h1 className="text-5xl sm:text-6xl font-black tracking-wider mb-3" style={{ fontFamily: 'Georgia, serif' }}>
          <span className="gold-text">TEEN PATTI</span>
        </h1>
        <p className="text-yellow-500/50 tracking-[0.4em] uppercase text-sm font-semibold mb-4">Playroom</p>
        <p className="text-white/50 text-lg mb-10 leading-relaxed">
          The premium Indian card game experience.<br />
          Play with friends. Win big. Play responsibly.
        </p>

        <button
          onClick={handlePlay}
          className="px-12 py-4 rounded-xl font-black text-black text-xl transition-all active:scale-95 hover:scale-105 mb-8"
          style={{
            background: 'linear-gradient(135deg, #d4af37 0%, #f0c030 50%, #d4af37 100%)',
            boxShadow: '0 6px 30px rgba(212,175,55,0.5), inset 0 1px 0 rgba(255,255,255,0.3)',
            letterSpacing: '0.08em',
          }}
        >
          {user ? 'ENTER LOBBY' : 'PLAY NOW'}
        </button>

        <div className="flex flex-wrap justify-center gap-3">
          {[
            { icon: '🎴', text: 'Classic Teen Patti' },
            { icon: '🏆', text: 'Live Tournaments' },
            { icon: '💰', text: 'Daily Bonus Chips' },
            { icon: '🔐', text: 'Secure & Fair' },
          ].map(f => (
            <div
              key={f.text}
              className="flex items-center gap-2 px-3 py-2 rounded-full text-sm text-white/55"
              style={{ border: '1px solid rgba(255,255,255,0.08)', background: 'rgba(255,255,255,0.03)' }}
            >
              <span>{f.icon}</span>
              <span>{f.text}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default Index;
