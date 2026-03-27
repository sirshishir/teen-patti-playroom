import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useGame } from '@/contexts/GameContext';
import { useAuth } from '@/contexts/AuthContext';
import { useToast } from '@/hooks/use-toast';

// ── Types ──────────────────────────────────────────────────────────────────
type Card = { suit: 'hearts' | 'diamonds' | 'clubs' | 'spades'; value: number };
type Phase = 'dealing' | 'playing' | 'showdown';

// ── Helpers ────────────────────────────────────────────────────────────────
const SUIT_SYMBOL: Record<string, string> = { hearts: '♥', diamonds: '♦', clubs: '♣', spades: '♠' };
const IS_RED = (s: string) => s === 'hearts' || s === 'diamonds';
const cardName = (v: number) =>
  v === 1 ? 'A' : v === 11 ? 'J' : v === 12 ? 'Q' : v === 13 ? 'K' : String(v);

// ── PlayingCard ─────────────────────────────────────────────────────────────
interface CardProps {
  card?: Card;
  faceDown?: boolean;
  delay?: number;
  animate?: boolean;
  small?: boolean;
  direction?: 'down' | 'up';
}

const PlayingCard: React.FC<CardProps> = ({
  card, faceDown = false, delay = 0, animate = false, small = false, direction = 'down',
}) => {
  const [visible, setVisible] = useState(false);
  const [flipped, setFlipped] = useState(false);

  useEffect(() => {
    if (!animate) return;
    const t = setTimeout(() => setVisible(true), delay);
    return () => clearTimeout(t);
  }, [animate, delay]);

  useEffect(() => {
    if (visible && !faceDown) {
      const t = setTimeout(() => setFlipped(true), 300);
      return () => clearTimeout(t);
    }
    if (faceDown) setFlipped(false);
  }, [visible, faceDown]);

  const W = small ? 36 : 60;
  const H = small ? 52 : 88;
  const dealClass = direction === 'down' ? 'card-deal-down' : 'card-deal-up';

  return (
    <div
      className={visible ? dealClass : ''}
      style={{ width: W, height: H, flexShrink: 0, perspective: 800, opacity: visible ? undefined : 0 }}
    >
      <div
        style={{
          width: '100%', height: '100%',
          transformStyle: 'preserve-3d',
          transition: 'transform 0.45s ease',
          transform: flipped ? 'rotateY(180deg)' : 'rotateY(0deg)',
          position: 'relative',
        }}
      >
        {/* ─ Card Back ─ */}
        <div
          className="absolute inset-0 rounded-lg shadow-2xl overflow-hidden"
          style={{ backfaceVisibility: 'hidden', WebkitBackfaceVisibility: 'hidden' }}
        >
          <div className="w-full h-full flex items-center justify-center"
            style={{ background: 'linear-gradient(135deg, #1a3a8f 0%, #0d2260 100%)', border: '2px solid rgba(255,255,255,0.15)', borderRadius: 8 }}
          >
            <div style={{
              width: '82%', height: '82%',
              border: '1px solid rgba(100,149,237,0.35)', borderRadius: 4,
              backgroundImage: 'repeating-linear-gradient(45deg, rgba(255,255,255,0.03) 0px, rgba(255,255,255,0.03) 1px, transparent 1px, transparent 7px)',
            }} />
          </div>
        </div>

        {/* ─ Card Front ─ */}
        <div
          className="absolute inset-0 rounded-lg shadow-2xl bg-white overflow-hidden"
          style={{ backfaceVisibility: 'hidden', WebkitBackfaceVisibility: 'hidden', transform: 'rotateY(180deg)', border: '1px solid #e5e7eb' }}
        >
          {card && (
            <div className="w-full h-full flex flex-col" style={{ color: IS_RED(card.suit) ? '#dc2626' : '#111827', padding: small ? 3 : 5 }}>
              <div style={{ lineHeight: 1 }}>
                <div style={{ fontWeight: 800, fontSize: small ? 9 : 14 }}>{cardName(card.value)}</div>
                <div style={{ fontSize: small ? 8 : 12 }}>{SUIT_SYMBOL[card.suit]}</div>
              </div>
              <div className="flex-1 flex items-center justify-center" style={{ fontSize: small ? 18 : 32 }}>
                {SUIT_SYMBOL[card.suit]}
              </div>
              <div style={{ lineHeight: 1, alignSelf: 'flex-end', transform: 'rotate(180deg)' }}>
                <div style={{ fontWeight: 800, fontSize: small ? 9 : 14 }}>{cardName(card.value)}</div>
                <div style={{ fontSize: small ? 8 : 12 }}>{SUIT_SYMBOL[card.suit]}</div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

// ── ChipBadge ──────────────────────────────────────────────────────────────
const ChipBadge: React.FC<{ amount: number }> = ({ amount }) => (
  <div className="flex items-center gap-1 rounded-full px-2 py-0.5"
    style={{ background: 'rgba(0,0,0,0.55)', border: '1px solid rgba(212,175,55,0.4)' }}
  >
    <div className="w-3 h-3 rounded-full bg-yellow-400 border border-yellow-600 flex-shrink-0" />
    <span className="text-yellow-300 font-bold" style={{ fontSize: 11 }}>₹{amount.toLocaleString()}</span>
  </div>
);

// ── Opponent Seat ──────────────────────────────────────────────────────────
interface OpponentProps {
  name: string; photoURL: string; balance: number; bet: number;
  cards: Card[]; animate: boolean; dealOffset: number; isTurn: boolean; folded?: boolean;
}

const OpponentSeat: React.FC<OpponentProps> = ({ name, photoURL, balance, bet, cards, animate, dealOffset, isTurn, folded }) => (
  <div className={`flex flex-col items-center gap-1 transition-opacity duration-500 ${folded ? 'opacity-30' : ''}`}>
    <div className="flex gap-1">
      {cards.map((_, i) => (
        <PlayingCard key={i} faceDown animate={animate} delay={dealOffset + i * 400} small direction="down" />
      ))}
    </div>
    <div
      className={`flex flex-col items-center gap-1 rounded-xl px-3 py-2 ${isTurn ? 'turn-glow' : ''}`}
      style={{
        background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(8px)',
        border: isTurn ? '1px solid rgba(250,204,21,0.7)' : '1px solid rgba(255,255,255,0.1)',
      }}
    >
      <div className="relative rounded-full overflow-hidden"
        style={{ width: 46, height: 46, border: isTurn ? '2px solid #facc15' : '2px solid rgba(255,255,255,0.25)' }}
      >
        <img src={photoURL} alt={name} className="w-full h-full object-cover" />
        {isTurn && <div className="absolute inset-0 bg-yellow-300/10 animate-pulse" />}
      </div>
      <span className="text-white font-semibold truncate" style={{ fontSize: 11, maxWidth: 68 }}>{name}</span>
      <ChipBadge amount={balance} />
      {bet > 0 && <span className="text-yellow-300 font-semibold" style={{ fontSize: 10 }}>Bet ₹{bet}</span>}
    </div>
  </div>
);

// ── Static opponent data ───────────────────────────────────────────────────
const OPPONENTS = [
  { id: 'o1', name: 'Rahul K.',  photoURL: 'https://ui-avatars.com/api/?name=Rahul+K&background=b91c1c&color=fff',  balance: 2500, bet: 50, isTurn: false, folded: false },
  { id: 'o2', name: 'Priya S.',  photoURL: 'https://ui-avatars.com/api/?name=Priya+S&background=7c3aed&color=fff',  balance: 1200, bet: 50, isTurn: true,  folded: false },
  { id: 'o3', name: 'Amit V.',   photoURL: 'https://ui-avatars.com/api/?name=Amit+V&background=065f46&color=fff',   balance: 800,  bet: 50, isTurn: false, folded: false },
];

const DUMMY_CARDS: Card[] = [{ suit: 'hearts', value: 1 }, { suit: 'clubs', value: 7 }, { suit: 'spades', value: 13 }];

// ── GameRoom ───────────────────────────────────────────────────────────────
const GameRoom = () => {
  const { currentRoom, playerCards, leaveRoom, placeBet, fold, showCards } = useGame();
  const { user } = useAuth();
  const navigate = useNavigate();
  const { toast } = useToast();

  const [betAmount, setBetAmount] = useState(currentRoom?.minBet || 10);
  const [phase, setPhase] = useState<Phase>('dealing');
  const [animate, setAnimate] = useState(false);
  const [showLeave, setShowLeave] = useState(false);
  const [userFaceDown, setUserFaceDown] = useState(true);

  // Round-robin deal: 3 opponents + user = 4 seats, 3 cards each = 12 deliveries
  // Seat i card j → delay = (j*4 + i) * 350ms
  // User = seat 3: card j → (j*4 + 3) * 350
  const DEAL_DONE_MS = (2 * 4 + 3) * 350 + 400 + 800; // last card delay + slide + buffer

  useEffect(() => {
    if (!currentRoom) { navigate('/lobby'); return; }
    const t1 = setTimeout(() => setAnimate(true), 120);
    const t2 = setTimeout(() => { setPhase('playing'); setUserFaceDown(false); }, DEAL_DONE_MS);
    return () => { clearTimeout(t1); clearTimeout(t2); };
  }, []);

  if (!currentRoom) return null;

  const isPlaying = phase === 'playing';

  const handleCall  = () => { placeBet(currentRoom.minBet); toast({ title: `Called ₹${currentRoom.minBet}` }); };
  const handleRaise = () => { placeBet(betAmount); toast({ title: `Raised ₹${betAmount}` }); };
  const handleFold  = () => { fold(); navigate('/lobby'); toast({ title: 'You folded.' }); };
  const handleShow  = () => { showCards(); setPhase('showdown'); toast({ title: 'Cards shown!' }); };

  return (
    <div
      className="min-h-screen flex flex-col select-none"
      style={{ background: 'radial-gradient(ellipse at 50% 30%, #1a0d3a 0%, #0a0618 70%, #000 100%)' }}
    >
      <div className="h-0.5 flex-shrink-0" style={{ background: 'linear-gradient(90deg, transparent, #d4af37, #f0d060, #d4af37, transparent)' }} />

      {/* ── Header ── */}
      <header
        className="flex items-center justify-between px-4 py-2.5 flex-shrink-0"
        style={{ background: 'rgba(0,0,0,0.5)', backdropFilter: 'blur(10px)', borderBottom: '1px solid rgba(212,175,55,0.12)' }}
      >
        <div className="flex items-center gap-2">
          <span className="gold-text font-black tracking-wider text-lg" style={{ fontFamily: 'Georgia, serif' }}>TEEN PATTI</span>
          <span className="text-white/30 text-xs">|</span>
          <span className="text-white/60 text-sm">{currentRoom.name}</span>
        </div>
        <div className="flex items-center gap-3">
          <ChipBadge amount={user?.balance || 0} />
          <button
            onClick={() => setShowLeave(true)}
            className="px-3 py-1.5 rounded-lg text-sm font-bold text-white/80 hover:text-white transition-colors"
            style={{ background: 'rgba(185,28,28,0.3)', border: '1px solid rgba(185,28,28,0.4)' }}
          >
            Leave
          </button>
        </div>
      </header>

      {/* ── Game area ── */}
      <div className="flex-1 flex flex-col items-center justify-between py-4 px-3 gap-3 overflow-hidden">

        {/* Opponents */}
        <div className="flex gap-4 sm:gap-8 justify-center items-end w-full max-w-2xl">
          {OPPONENTS.map((opp, i) => (
            <OpponentSeat
              key={opp.id}
              name={opp.name} photoURL={opp.photoURL} balance={opp.balance} bet={opp.bet}
              cards={DUMMY_CARDS}
              animate={animate}
              dealOffset={i * 350}
              isTurn={opp.isTurn} folded={opp.folded}
            />
          ))}
        </div>

        {/* ── Oval Poker Table ── */}
        <div
          className="relative flex items-center justify-center flex-shrink-0 table-felt"
          style={{
            width: 'min(620px, 92vw)',
            height: 'min(190px, 28vw)',
            minHeight: 120,
            borderRadius: '50%',
            border: '18px solid #3d200a',
            boxShadow: ['0 0 0 3px #7a4810', '0 0 0 5px #3d200a', 'inset 0 0 50px rgba(0,0,0,0.45)', '0 20px 60px rgba(0,0,0,0.7)'].join(', '),
          }}
        >
          {/* Inner gold rail */}
          <div className="absolute inset-2 rounded-[50%] pointer-events-none" style={{ border: '1px solid rgba(212,175,55,0.18)' }} />

          {/* Pot display */}
          <div className="relative z-10 flex flex-col items-center gap-1">
            <div className="flex items-center gap-2 rounded-full px-4 py-2 pot-pulse"
              style={{ background: 'rgba(0,0,0,0.6)', border: '1px solid rgba(212,175,55,0.4)', backdropFilter: 'blur(6px)' }}
            >
              <div className="flex">
                {['#e53e3e', '#d4af37', '#3182ce'].map((c, i) => (
                  <div key={i} className="w-5 h-5 rounded-full border-2" style={{ background: c, borderColor: c, marginLeft: i > 0 ? -7 : 0, zIndex: 3 - i }} />
                ))}
              </div>
              <span className="text-yellow-300 font-bold text-sm">POT ₹{currentRoom.pot.toLocaleString()}</span>
            </div>
            <span className="text-white/30 text-xs">Min ₹{currentRoom.minBet}</span>
          </div>

          {/* Dealer button */}
          <div
            className="absolute right-[13%] top-1/2 -translate-y-1/2 w-7 h-7 rounded-full flex items-center justify-center font-black text-xs"
            style={{ background: 'white', border: '2px solid #d4af37', color: '#1a1a2e', boxShadow: '0 2px 8px rgba(0,0,0,0.5)' }}
          >D</div>
        </div>

        {/* ── User area ── */}
        <div className="flex flex-col items-center gap-3 w-full max-w-md">
          {/* User cards — deal from below */}
          <div className="flex gap-3 justify-center">
            {playerCards.map((card, i) => (
              <PlayingCard
                key={i} card={card}
                faceDown={userFaceDown}
                animate={animate}
                delay={(i * 4 + 3) * 350}
                direction="up"
              />
            ))}
          </div>

          {/* User info */}
          <div
            className="flex items-center gap-3 rounded-xl px-4 py-2.5"
            style={{ background: 'rgba(0,0,0,0.6)', border: '1px solid rgba(212,175,55,0.3)', backdropFilter: 'blur(8px)', boxShadow: '0 4px 20px rgba(0,0,0,0.4)' }}
          >
            <div className="rounded-full overflow-hidden flex-shrink-0" style={{ width: 44, height: 44, border: '2px solid #d4af37' }}>
              <img src={user?.photoURL} alt={user?.name} className="w-full h-full object-cover" />
            </div>
            <div>
              <p className="text-white font-bold text-sm">{user?.name}</p>
              <ChipBadge amount={user?.balance || 0} />
            </div>
            <div className="ml-2 font-semibold" style={{ fontSize: 11, color: phase === 'playing' ? '#facc15' : 'rgba(255,255,255,0.4)' }}>
              {phase === 'dealing' ? 'WAITING…' : phase === 'playing' ? 'YOUR TURN' : 'SHOWDOWN'}
            </div>
          </div>
        </div>
      </div>

      {/* ── Action bar ── */}
      <div
        className="flex-shrink-0 px-4 py-3"
        style={{ background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(12px)', borderTop: '1px solid rgba(255,255,255,0.06)' }}
      >
        <div className="flex items-center justify-center gap-2 max-w-xl mx-auto flex-wrap">

          <button onClick={handleFold} disabled={!isPlaying}
            className="px-5 py-2.5 rounded-xl font-black text-sm transition-all active:scale-95 disabled:opacity-30 disabled:cursor-not-allowed"
            style={{ background: 'linear-gradient(135deg, #991b1b, #7f1d1d)', border: '1px solid rgba(239,68,68,0.4)', color: '#fca5a5', boxShadow: '0 4px 12px rgba(153,27,27,0.4)' }}
          >FOLD</button>

          <button onClick={handleCall} disabled={!isPlaying}
            className="px-5 py-2.5 rounded-xl font-black text-sm transition-all active:scale-95 disabled:opacity-30 disabled:cursor-not-allowed"
            style={{ background: 'linear-gradient(135deg, #1e40af, #1e3a8a)', border: '1px solid rgba(59,130,246,0.4)', color: '#93c5fd', boxShadow: '0 4px 12px rgba(30,64,175,0.4)' }}
          >CALL ₹{currentRoom.minBet}</button>

          {/* Bet size control */}
          <div className="flex items-center rounded-xl overflow-hidden" style={{ border: '1px solid rgba(255,255,255,0.12)', background: 'rgba(255,255,255,0.05)' }}>
            <button
              onClick={() => setBetAmount(v => Math.max(currentRoom.minBet, v - currentRoom.minBet))}
              disabled={!isPlaying}
              className="px-3 py-2.5 text-white/60 hover:text-yellow-400 font-black text-sm transition-colors disabled:opacity-30"
            >−</button>
            <span className="text-white font-bold text-sm min-w-[60px] text-center">₹{betAmount}</span>
            <button
              onClick={() => setBetAmount(v => v + currentRoom.minBet)}
              disabled={!isPlaying}
              className="px-3 py-2.5 text-white/60 hover:text-yellow-400 font-black text-sm transition-colors disabled:opacity-30"
            >+</button>
          </div>

          <button onClick={handleRaise} disabled={!isPlaying}
            className="px-5 py-2.5 rounded-xl font-black text-sm transition-all active:scale-95 disabled:opacity-30 disabled:cursor-not-allowed"
            style={{ background: 'linear-gradient(135deg, #d4af37, #b8860b)', border: '1px solid rgba(212,175,55,0.5)', color: '#000', boxShadow: '0 4px 16px rgba(212,175,55,0.35)' }}
          >RAISE ₹{betAmount}</button>

          <button onClick={handleShow} disabled={!isPlaying}
            className="px-5 py-2.5 rounded-xl font-black text-sm transition-all active:scale-95 disabled:opacity-30 disabled:cursor-not-allowed"
            style={{ background: 'linear-gradient(135deg, #065f46, #064e3b)', border: '1px solid rgba(52,211,153,0.35)', color: '#6ee7b7', boxShadow: '0 4px 12px rgba(6,95,70,0.4)' }}
          >SHOW</button>
        </div>
      </div>

      {/* ── Dealing overlay ── */}
      {phase === 'dealing' && (
        <div className="fixed inset-0 pointer-events-none flex items-center justify-center z-20">
          <div className="flex flex-col items-center gap-3 px-8 py-5 rounded-2xl scale-in"
            style={{ background: 'rgba(0,0,0,0.82)', border: '1px solid rgba(212,175,55,0.35)', backdropFilter: 'blur(8px)' }}
          >
            <span className="text-yellow-400 font-black text-xl tracking-wider">Dealing Cards</span>
            <div className="flex gap-1.5">
              {[0, 1, 2].map(i => (
                <div key={i} className="w-2.5 h-2.5 rounded-full bg-yellow-400 dealing-dot" style={{ animationDelay: `${i * 0.2}s` }} />
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ── Leave confirmation ── */}
      {showLeave && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,0.8)', backdropFilter: 'blur(4px)' }}>
          <div className="w-full max-w-sm rounded-2xl p-6 scale-in"
            style={{ background: 'linear-gradient(135deg, #1a0d3a 0%, #100820 100%)', border: '1px solid rgba(212,175,55,0.3)', boxShadow: '0 30px 80px rgba(0,0,0,0.7)' }}
          >
            <h3 className="text-white text-lg font-bold mb-2">Leave the Table?</h3>
            <p className="text-white/50 text-sm mb-6">Your current bet will be lost.</p>
            <div className="flex gap-3">
              <button onClick={() => setShowLeave(false)}
                className="flex-1 py-3 rounded-xl text-white/60 hover:text-white font-semibold transition-colors"
                style={{ border: '1px solid rgba(255,255,255,0.1)' }}
              >Stay</button>
              <button onClick={() => { leaveRoom(); navigate('/lobby'); }}
                className="flex-1 py-3 rounded-xl font-bold text-white transition-all active:scale-95"
                style={{ background: 'linear-gradient(135deg, #991b1b, #7f1d1d)', border: '1px solid rgba(239,68,68,0.3)' }}
              >Leave</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default GameRoom;
