import React, { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { useGame } from '@/contexts/GameContext';
import { Input } from '@/components/ui/input';
import { useToast } from '@/hooks/use-toast';
import { LogOut, ChevronDown, ChevronUp, Users } from 'lucide-react';

// ─── Types ────────────────────────────────────────────────────────────────────

type LobbyRoom = {
  id: string;
  code: string;
  name: string;
  playerCount: number;
  maxPlayers: number;
  minBet: number;
  status: 'waiting' | 'playing';
};

// ─── Sub-components ───────────────────────────────────────────────────────────

const GoldChipIcon: React.FC<{ size?: number }> = ({ size = 18 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
    <circle cx="12" cy="12" r="10" fill="#d4af37" stroke="#b8902a" strokeWidth="1.5" />
    <circle cx="12" cy="12" r="7" fill="none" stroke="#b8902a" strokeWidth="1" strokeDasharray="2 2" />
    <text x="12" y="16" textAnchor="middle" fontSize="9" fontWeight="bold" fill="#5a3a00">₹</text>
  </svg>
);

const StakeBadge: React.FC<{ minBet: number }> = ({ minBet }) => {
  const tier =
    minBet >= 500
      ? { label: 'HIGH', color: '#e53e3e', bg: 'rgba(229,62,62,0.15)', border: 'rgba(229,62,62,0.35)' }
      : minBet >= 100
      ? { label: 'MID', color: '#d4af37', bg: 'rgba(212,175,55,0.15)', border: 'rgba(212,175,55,0.35)' }
      : { label: 'LOW', color: '#38a169', bg: 'rgba(56,161,105,0.15)', border: 'rgba(56,161,105,0.35)' };
  return (
    <span
      className="text-xs font-bold px-2 py-0.5 rounded-full tracking-widest"
      style={{ color: tier.color, background: tier.bg, border: `1px solid ${tier.border}` }}
    >
      {tier.label}
    </span>
  );
};

const PlayerDots: React.FC<{ count: number; max: number }> = ({ count, max }) => {
  const visible = Math.min(count, 4);
  const colors = ['#d4af37', '#7c3aed', '#2563eb', '#dc2626'];
  return (
    <div className="flex items-center -space-x-2">
      {Array.from({ length: visible }).map((_, i) => (
        <div
          key={i}
          className="w-6 h-6 rounded-full border-2 flex items-center justify-center text-[9px] font-bold text-white"
          style={{ borderColor: '#1a0d3a', background: colors[i % colors.length], zIndex: visible - i }}
        >
          {String.fromCharCode(65 + i)}
        </div>
      ))}
      {count > 4 && (
        <div
          className="w-6 h-6 rounded-full border-2 flex items-center justify-center text-[9px] font-bold text-white/70"
          style={{ borderColor: '#1a0d3a', background: 'rgba(255,255,255,0.15)', zIndex: 0 }}
        >
          +{count - 4}
        </div>
      )}
      <span className="ml-3 text-white/40 text-xs">{count}/{max}</span>
    </div>
  );
};

const MiniTable: React.FC<{ status: 'waiting' | 'playing' }> = ({ status }) => (
  <div
    className="relative flex items-center justify-center"
    style={{
      width: 140,
      height: 70,
      background: 'radial-gradient(ellipse, #226b3a 0%, #145025 100%)',
      borderRadius: '50%',
      border: '8px solid #3d1f06',
      boxShadow: '0 0 0 2px #7a4a10, inset 0 0 18px rgba(0,0,0,0.45)',
    }}
  >
    {[
      { left: '28%', rotate: '-14deg' },
      { left: '43%', rotate: '0deg' },
      { left: '58%', rotate: '13deg' },
    ].map((c, i) => (
      <div
        key={i}
        className="absolute rounded-sm"
        style={{
          width: 12,
          height: 18,
          left: c.left,
          top: '50%',
          transform: `translateY(-50%) rotate(${c.rotate})`,
          background: i % 2 === 0 ? '#1a4b8f' : '#f5f5f5',
          boxShadow: '0 2px 4px rgba(0,0,0,0.5)',
        }}
      />
    ))}
    <div
      className="absolute bottom-[-4px] left-1/2 -translate-x-1/2 w-3 h-3 rounded-full"
      style={{
        background: status === 'waiting' ? '#4ade80' : '#f59e0b',
        boxShadow: status === 'waiting' ? '0 0 8px #4ade80' : '0 0 8px #f59e0b',
      }}
    />
  </div>
);

// ─── Hand Rankings Section ────────────────────────────────────────────────────

const HAND_RANKINGS = [
  { name: 'Trail', sub: 'Three of a Kind', symbols: '♠♥♦', example: 'A A A', color: '#d4af37' },
  { name: 'Pure Sequence', sub: 'Straight Flush', symbols: '♣♣♣', example: 'A K Q ♣', color: '#7c3aed' },
  { name: 'Sequence', sub: 'Straight', symbols: '♠♥♦', example: 'A K Q', color: '#2563eb' },
  { name: 'Color', sub: 'Flush', symbols: '♥♥♥', example: 'A J 8 ♥', color: '#dc2626' },
  { name: 'Pair', sub: 'Two of a Kind', symbols: '♠♠♦', example: 'A A K', color: '#059669' },
  { name: 'High Card', sub: 'Highest card wins', symbols: '♠♥♣', example: 'A K J', color: '#6b7280' },
];

const HowToPlay: React.FC = () => {
  const [open, setOpen] = useState(false);
  return (
    <div
      className="rounded-2xl overflow-hidden mt-10"
      style={{
        background: 'rgba(255,255,255,0.02)',
        border: '1px solid rgba(255,255,255,0.07)',
      }}
    >
      <button
        className="w-full flex items-center justify-between px-6 py-4 text-left"
        onClick={() => setOpen(o => !o)}
      >
        <span className="text-white/70 font-semibold tracking-wide text-sm uppercase">
          How to Play — Hand Rankings
        </span>
        {open ? <ChevronUp size={18} className="text-white/40" /> : <ChevronDown size={18} className="text-white/40" />}
      </button>
      {open && (
        <div className="px-6 pb-6 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          {HAND_RANKINGS.map((h, i) => (
            <div
              key={h.name}
              className="rounded-xl p-3 text-center fade-in-up"
              style={{
                background: 'rgba(255,255,255,0.03)',
                border: `1px solid ${h.color}33`,
                animationDelay: `${i * 60}ms`,
              }}
            >
              <div className="text-lg mb-1" style={{ color: h.color }}>
                {h.symbols}
              </div>
              <p className="text-white text-xs font-bold leading-tight">{h.name}</p>
              <p className="text-white/40 text-[10px] mt-0.5">{h.sub}</p>
              <p className="text-white/25 text-[10px] mt-1 font-mono">{h.example}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

// ─── Main Lobby ───────────────────────────────────────────────────────────────

const Lobby: React.FC = () => {
  const { user, logout } = useAuth();
  const { lobbyRooms, createRoom, joinRoom, joinRoomByCode } = useGame() as {
    lobbyRooms: LobbyRoom[];
    createRoom: (name: string, minBet: number, maxPlayers: number, fillWithBots: boolean) => void;
    joinRoom: (roomId: string) => void;
    joinRoomByCode: (code: string) => boolean;
  };
  const navigate = useNavigate();
  const { toast } = useToast();

  // Create room state
  const [roomName, setRoomName] = useState('');
  const [minBet, setMinBet] = useState(50);
  const [maxPlayers, setMaxPlayers] = useState(6);
  const [fillWithBots, setFillWithBots] = useState(true);

  // Join by code state
  const [codeInput, setCodeInput] = useState('');
  const [codeError, setCodeError] = useState(false);
  const codeInputRef = useRef<HTMLInputElement>(null);
  const shakeTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (shakeTimeoutRef.current) clearTimeout(shakeTimeoutRef.current);
    };
  }, []);

  // ── Handlers ──

  const handleCreateRoom = () => {
    const name = roomName.trim() || 'My Table';
    createRoom(name, minBet, maxPlayers, fillWithBots);
    setRoomName('');
    toast({ title: 'Table created!', description: `"${name}" is ready.` });
    navigate('/game');
  };

  const handleJoinRoom = (roomId: string) => {
    joinRoom(roomId);
    navigate('/game');
  };

  const triggerCodeError = () => {
    setCodeError(true);
    if (shakeTimeoutRef.current) clearTimeout(shakeTimeoutRef.current);
    shakeTimeoutRef.current = setTimeout(() => setCodeError(false), 700);
  };

  const handleJoinByCode = (code: string = codeInput) => {
    const clean = code.trim().toUpperCase();
    if (clean.length !== 6) return;
    const ok = joinRoomByCode(clean);
    if (ok) {
      navigate('/game');
    } else {
      triggerCodeError();
      toast({ title: 'Room not found', description: `No table with code "${clean}".`, variant: 'destructive' });
    }
  };

  const handleCodeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value.replace(/[^a-zA-Z0-9]/g, '').toUpperCase().slice(0, 6);
    setCodeInput(val);
    setCodeError(false);
    if (val.length === 6) {
      // auto-submit
      handleJoinByCode(val);
    }
  };

  const handleLogout = async () => {
    await logout();
    navigate('/');
  };

  // ── Shared styles ──

  const glassCard: React.CSSProperties = {
    background: 'rgba(255,255,255,0.03)',
    border: '1px solid rgba(255,255,255,0.09)',
    backdropFilter: 'blur(12px)',
    borderRadius: '1.25rem',
  };

  const goldBtn: React.CSSProperties = {
    background: 'linear-gradient(135deg, #d4af37 0%, #f0c030 50%, #d4af37 100%)',
    boxShadow: '0 4px 20px rgba(212,175,55,0.4)',
    color: '#1a0a00',
    fontWeight: 800,
    letterSpacing: '0.08em',
    borderRadius: '0.75rem',
    border: 'none',
    cursor: 'pointer',
    transition: 'transform 0.12s, box-shadow 0.12s',
  };

  const selectorBtn = (active: boolean): React.CSSProperties => ({
    background: active ? 'rgba(212,175,55,0.18)' : 'rgba(255,255,255,0.04)',
    border: active ? '1px solid rgba(212,175,55,0.55)' : '1px solid rgba(255,255,255,0.09)',
    color: active ? '#f0d060' : 'rgba(255,255,255,0.45)',
    fontWeight: 700,
    borderRadius: '0.5rem',
    cursor: 'pointer',
    transition: 'all 0.15s',
  });

  const labelStyle: React.CSSProperties = {
    color: 'rgba(255,255,255,0.5)',
    fontSize: '0.7rem',
    fontWeight: 700,
    textTransform: 'uppercase',
    letterSpacing: '0.1em',
    display: 'block',
    marginBottom: '0.5rem',
  };

  return (
    <div
      className="min-h-screen"
      style={{ background: 'radial-gradient(ellipse at 50% 0%, #1a0d3a 0%, #0a0618 60%, #000 100%)' }}
    >
      {/* Gold top bar */}
      <div
        style={{
          height: 2,
          background: 'linear-gradient(90deg, transparent 0%, #d4af37 30%, #f0d060 50%, #d4af37 70%, transparent 100%)',
        }}
      />

      {/* ── Sticky Header ── */}
      <header
        className="sticky top-0 z-30 px-4 sm:px-8 py-3 flex items-center justify-between"
        style={{
          background: 'rgba(10,6,24,0.92)',
          backdropFilter: 'blur(16px)',
          borderBottom: '1px solid rgba(212,175,55,0.13)',
        }}
      >
        {/* Logo */}
        <div className="flex items-center gap-2 select-none">
          <span
            className="text-xl sm:text-2xl font-black tracking-widest"
            style={{
              fontFamily: 'Georgia, serif',
              background: 'linear-gradient(135deg, #d4af37 0%, #f0d060 50%, #b8902a 100%)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              backgroundClip: 'text',
            }}
          >
            TEEN PATTI PLAYROOM
          </span>
        </div>

        {/* Right: balance + avatar + logout */}
        <div className="flex items-center gap-3">
          {user && (
            <>
              {/* Balance */}
              <div
                className="hidden sm:flex items-center gap-1.5 px-3 py-1.5 rounded-full"
                style={{ background: 'rgba(212,175,55,0.08)', border: '1px solid rgba(212,175,55,0.2)' }}
              >
                <GoldChipIcon size={16} />
                <span className="text-yellow-300 font-bold text-sm">
                  ₹{user.balance.toLocaleString()}
                </span>
              </div>

              {/* Avatar + name */}
              <div className="flex items-center gap-2">
                <img
                  src={user.photoURL}
                  alt={user.name}
                  className="w-8 h-8 rounded-full object-cover"
                  style={{ border: '2px solid rgba(212,175,55,0.5)' }}
                />
                <span className="hidden md:block text-white/70 text-sm font-medium max-w-[120px] truncate">
                  {user.name}
                </span>
              </div>

              {/* Logout */}
              <button
                onClick={handleLogout}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-white/50 hover:text-white/80 transition-colors text-sm"
                style={{ border: '1px solid rgba(255,255,255,0.08)' }}
                title="Logout"
              >
                <LogOut size={15} />
                <span className="hidden sm:inline">Logout</span>
              </button>
            </>
          )}
        </div>
      </header>

      {/* ── Main ── */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-8">
        {/* Welcome */}
        <div className="mb-8 fade-in-up">
          <h1 className="text-white text-2xl sm:text-3xl font-bold mb-1">
            Welcome back,{' '}
            <span style={{ color: '#d4af37' }}>{user?.name?.split(' ')[0] ?? 'Player'}</span>
          </h1>
          <p className="text-white/35 text-sm">Choose a table or create your own.</p>
        </div>

        {/* Two-column layout */}
        <div className="flex flex-col lg:flex-row gap-6">
          {/* ── LEFT: Quick Actions ── */}
          <div className="flex flex-col gap-5 lg:w-[360px] flex-shrink-0">

            {/* Create Room Panel */}
            <div className="p-5 fade-in-up" style={{ ...glassCard, animationDelay: '60ms' }}>
              <h2
                className="text-base font-bold tracking-wide mb-4"
                style={{ color: '#d4af37', fontFamily: 'Georgia, serif' }}
              >
                CREATE A TABLE
              </h2>

              {/* Room name */}
              <div className="mb-4">
                <label style={labelStyle}>Table Name</label>
                <Input
                  value={roomName}
                  onChange={e => setRoomName(e.target.value)}
                  placeholder="My Table"
                  maxLength={32}
                  className="bg-white/5 border-white/10 text-white placeholder:text-white/20 focus:border-yellow-500/50"
                  onKeyDown={e => e.key === 'Enter' && handleCreateRoom()}
                />
              </div>

              {/* Min bet */}
              <div className="mb-4">
                <label style={labelStyle}>Minimum Bet</label>
                <div className="flex gap-2 flex-wrap">
                  {[10, 25, 50, 100, 500].map(val => (
                    <button
                      key={val}
                      onClick={() => setMinBet(val)}
                      className="flex-1 min-w-[48px] py-2 text-sm transition-all active:scale-95"
                      style={selectorBtn(minBet === val)}
                    >
                      ₹{val}
                    </button>
                  ))}
                </div>
              </div>

              {/* Max players */}
              <div className="mb-4">
                <label style={labelStyle}>Max Players</label>
                <div className="flex gap-2">
                  {[2, 3, 4, 5, 6].map(n => (
                    <button
                      key={n}
                      onClick={() => setMaxPlayers(n)}
                      className="flex-1 py-2 text-sm transition-all active:scale-95"
                      style={selectorBtn(maxPlayers === n)}
                    >
                      {n}
                    </button>
                  ))}
                </div>
              </div>

              {/* Fill with bots toggle */}
              <div className="mb-5 flex items-center justify-between">
                <span className="text-white/55 text-sm">Fill empty seats with bots</span>
                <button
                  onClick={() => setFillWithBots(b => !b)}
                  className="relative w-11 h-6 rounded-full transition-colors duration-200 flex-shrink-0"
                  style={{
                    background: fillWithBots
                      ? 'linear-gradient(135deg, #d4af37, #b8902a)'
                      : 'rgba(255,255,255,0.12)',
                    border: fillWithBots ? '1px solid #d4af37' : '1px solid rgba(255,255,255,0.15)',
                  }}
                  aria-checked={fillWithBots}
                  role="switch"
                >
                  <span
                    className="absolute top-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform duration-200"
                    style={{ transform: fillWithBots ? 'translateX(20px)' : 'translateX(2px)' }}
                  />
                </button>
              </div>

              <button
                onClick={handleCreateRoom}
                className="w-full py-3 text-sm tracking-widest transition-all active:scale-95 hover:brightness-110"
                style={goldBtn}
              >
                CREATE ROOM
              </button>
            </div>

            {/* Join by Code Panel */}
            <div className="p-5 fade-in-up" style={{ ...glassCard, animationDelay: '120ms' }}>
              <h2
                className="text-base font-bold tracking-wide mb-1"
                style={{ color: '#d4af37', fontFamily: 'Georgia, serif' }}
              >
                HAVE A CODE?
              </h2>
              <p className="text-white/35 text-xs mb-4">Enter a 6-character room code to join instantly.</p>

              {/* Code input */}
              <div
                className={`flex gap-3 items-stretch ${codeError ? 'animate-shake' : ''}`}
                style={
                  codeError
                    ? { animation: 'shake 0.5s ease-in-out' }
                    : {}
                }
              >
                <div className="relative flex-1">
                  <input
                    ref={codeInputRef}
                    type="text"
                    value={codeInput}
                    onChange={handleCodeChange}
                    placeholder="XXXXXX"
                    maxLength={6}
                    spellCheck={false}
                    autoCapitalize="characters"
                    className="w-full py-3 text-center text-2xl font-black tracking-[0.45em] rounded-xl outline-none transition-all"
                    style={{
                      background: 'rgba(0,0,0,0.45)',
                      border: codeError
                        ? '1px solid #e53e3e'
                        : codeInput.length > 0
                        ? '1px solid rgba(212,175,55,0.5)'
                        : '1px solid rgba(255,255,255,0.1)',
                      color: codeError ? '#fc8181' : '#d4af37',
                      boxShadow: codeError
                        ? '0 0 0 3px rgba(229,62,62,0.15)'
                        : codeInput.length > 0
                        ? '0 0 0 3px rgba(212,175,55,0.12), 0 0 20px rgba(212,175,55,0.08)'
                        : 'none',
                      letterSpacing: '0.45em',
                      fontFamily: 'monospace',
                    }}
                    onFocus={e =>
                      (e.currentTarget.style.boxShadow = codeError
                        ? '0 0 0 3px rgba(229,62,62,0.2)'
                        : '0 0 0 3px rgba(212,175,55,0.2), 0 0 24px rgba(212,175,55,0.12)')
                    }
                    onBlur={e => (e.currentTarget.style.boxShadow = 'none')}
                    onKeyDown={e => e.key === 'Enter' && handleJoinByCode()}
                  />
                </div>

                <button
                  onClick={() => handleJoinByCode()}
                  disabled={codeInput.length !== 6}
                  className="px-4 py-3 rounded-xl font-bold tracking-wider text-sm transition-all active:scale-95"
                  style={{
                    ...(codeInput.length === 6 ? goldBtn : {}),
                    background:
                      codeInput.length === 6
                        ? 'linear-gradient(135deg, #d4af37 0%, #f0c030 100%)'
                        : 'rgba(255,255,255,0.06)',
                    color: codeInput.length === 6 ? '#1a0a00' : 'rgba(255,255,255,0.25)',
                    border:
                      codeInput.length === 6
                        ? 'none'
                        : '1px solid rgba(255,255,255,0.08)',
                    cursor: codeInput.length === 6 ? 'pointer' : 'not-allowed',
                    boxShadow:
                      codeInput.length === 6 ? '0 4px 16px rgba(212,175,55,0.35)' : 'none',
                  }}
                >
                  JOIN
                </button>
              </div>

              {/* Error message */}
              {codeError && (
                <p
                  className="text-xs mt-2 font-semibold"
                  style={{ color: '#fc8181' }}
                >
                  Room not found. Check the code and try again.
                </p>
              )}

              <p className="text-white/20 text-[11px] mt-3 text-center">
                Auto-joins when all 6 characters are entered
              </p>
            </div>
          </div>

          {/* ── RIGHT: Browse Rooms ── */}
          <div className="flex-1 min-w-0 fade-in-up" style={{ animationDelay: '80ms' }}>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-white font-bold text-lg flex items-center gap-2">
                <span
                  className="inline-block w-2 h-2 rounded-full"
                  style={{ background: '#4ade80', boxShadow: '0 0 8px rgba(74,222,128,0.8)' }}
                />
                Browse Tables
                <span className="text-white/30 text-sm font-normal ml-1">
                  ({lobbyRooms?.length ?? 0})
                </span>
              </h2>
            </div>

            {/* Room cards grid */}
            {lobbyRooms && lobbyRooms.length > 0 ? (
              <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
                {lobbyRooms.map((room, idx) => {
                  const isOpen = room.status === 'waiting' && room.playerCount < room.maxPlayers;
                  return (
                    <div
                      key={room.id}
                      className="rounded-2xl overflow-hidden fade-in-up"
                      style={{
                        background:
                          'linear-gradient(160deg, rgba(255,255,255,0.055) 0%, rgba(255,255,255,0.02) 100%)',
                        border: '1px solid rgba(255,255,255,0.08)',
                        animationDelay: `${idx * 70}ms`,
                      }}
                    >
                      {/* Felt preview area */}
                      <div
                        className="relative h-28 flex items-center justify-center overflow-hidden"
                        style={{
                          background:
                            'radial-gradient(ellipse at center, #1e5c30 0%, #0d3018 100%)',
                          borderBottom: '1px solid rgba(255,255,255,0.05)',
                        }}
                      >
                        <MiniTable status={room.status} />

                        {/* Status pill */}
                        <div
                          className="absolute top-3 left-3 flex items-center gap-1.5 px-2 py-0.5 rounded-full"
                          style={{ background: 'rgba(0,0,0,0.55)', backdropFilter: 'blur(4px)' }}
                        >
                          <span
                            className="w-1.5 h-1.5 rounded-full"
                            style={{
                              background: room.status === 'waiting' ? '#4ade80' : '#f59e0b',
                              boxShadow:
                                room.status === 'waiting'
                                  ? '0 0 6px #4ade80'
                                  : '0 0 6px #f59e0b',
                            }}
                          />
                          <span className="text-white/70 text-[10px] font-semibold">
                            {room.status === 'waiting' ? 'Open' : 'In Progress'}
                          </span>
                        </div>

                        {/* Code pill */}
                        {room.code && (
                          <div
                            className="absolute top-3 right-3 px-2 py-0.5 rounded-full font-mono text-[10px] font-bold tracking-widest"
                            style={{
                              background: 'rgba(0,0,0,0.55)',
                              backdropFilter: 'blur(4px)',
                              color: 'rgba(212,175,55,0.8)',
                            }}
                          >
                            {room.code}
                          </div>
                        )}
                      </div>

                      {/* Card body */}
                      <div className="p-4">
                        {/* Name + stake */}
                        <div className="flex items-center gap-2 mb-2 flex-wrap">
                          <h3 className="text-white font-bold text-sm truncate">{room.name}</h3>
                          <StakeBadge minBet={room.minBet} />
                        </div>

                        {/* Players */}
                        <div className="mb-3">
                          <PlayerDots count={room.playerCount} max={room.maxPlayers} />
                        </div>

                        {/* Min bet */}
                        <div className="flex items-center justify-between text-xs mb-4">
                          <span className="text-white/40 flex items-center gap-1">
                            <Users size={11} />
                            {room.playerCount}/{room.maxPlayers} players
                          </span>
                          <span className="text-white/40">
                            Min bet:{' '}
                            <span className="text-yellow-400 font-semibold">₹{room.minBet}</span>
                          </span>
                        </div>

                        {/* Join button */}
                        <button
                          onClick={() => isOpen && handleJoinRoom(room.id)}
                          disabled={!isOpen}
                          className="w-full py-2.5 rounded-xl font-bold text-sm tracking-wide transition-all active:scale-95"
                          style={{
                            background: isOpen
                              ? 'linear-gradient(135deg, #1e6b35 0%, #145025 100%)'
                              : 'rgba(255,255,255,0.04)',
                            border: isOpen
                              ? '1px solid rgba(74,222,128,0.35)'
                              : '1px solid rgba(255,255,255,0.07)',
                            color: isOpen ? '#4ade80' : 'rgba(255,255,255,0.25)',
                            cursor: isOpen ? 'pointer' : 'not-allowed',
                          }}
                        >
                          {isOpen ? 'JOIN TABLE' : room.status === 'playing' ? 'IN PROGRESS' : 'TABLE FULL'}
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              /* Empty state */
              <div
                className="flex flex-col items-center justify-center py-20 rounded-2xl fade-in-up"
                style={{
                  background: 'rgba(255,255,255,0.02)',
                  border: '1px dashed rgba(255,255,255,0.08)',
                }}
              >
                {/* Decorative card illustration */}
                <div className="relative mb-6">
                  {[
                    { rotate: '-18deg', x: '-24px', bg: '#1a4b8f', zIndex: 0 },
                    { rotate: '0deg', x: '0px', bg: '#f5f5f5', zIndex: 1 },
                    { rotate: '18deg', x: '24px', bg: '#7c1d1d', zIndex: 0 },
                  ].map((c, i) => (
                    <div
                      key={i}
                      className="absolute top-0 rounded-lg"
                      style={{
                        width: 48,
                        height: 68,
                        background: c.bg,
                        transform: `rotate(${c.rotate}) translateX(${c.x})`,
                        left: '50%',
                        marginLeft: -24,
                        zIndex: c.zIndex,
                        boxShadow: '0 4px 16px rgba(0,0,0,0.5)',
                        border: '1px solid rgba(255,255,255,0.1)',
                      }}
                    />
                  ))}
                  <div style={{ height: 80 }} />
                </div>
                <p className="text-white/40 text-base mb-2 font-semibold">No tables found</p>
                <p className="text-white/25 text-sm text-center max-w-xs">
                  Create one above and invite friends — or just play with bots!
                </p>
              </div>
            )}
          </div>
        </div>

        {/* How to Play */}
        <HowToPlay />
      </main>

      {/* Shake keyframes injected inline */}
      <style>{`
        @keyframes shake {
          0%   { transform: translateX(0); }
          15%  { transform: translateX(-8px); }
          30%  { transform: translateX(8px); }
          45%  { transform: translateX(-6px); }
          60%  { transform: translateX(6px); }
          75%  { transform: translateX(-3px); }
          90%  { transform: translateX(3px); }
          100% { transform: translateX(0); }
        }
      `}</style>
    </div>
  );
};

export default Lobby;
