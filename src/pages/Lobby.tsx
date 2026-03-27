import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { useGame } from '@/contexts/GameContext';
import { Input } from '@/components/ui/input';
import { useToast } from '@/hooks/use-toast';
import { LogOut, Plus, Users, Trophy, ChevronRight } from 'lucide-react';

const ChipBadge: React.FC<{ amount: number; className?: string }> = ({ amount, className = '' }) => (
  <div className={`flex items-center gap-1.5 ${className}`}>
    <div className="w-4 h-4 rounded-full border-2 border-yellow-500 bg-yellow-400 shadow-inner flex-shrink-0" />
    <span className="text-yellow-300 font-bold text-sm">₹{amount.toLocaleString()}</span>
  </div>
);

const StakeBadge: React.FC<{ minBet: number }> = ({ minBet }) => {
  const tier =
    minBet >= 500 ? { label: 'HIGH STAKES', color: '#e53e3e', bg: 'rgba(229,62,62,0.15)' } :
    minBet >= 100 ? { label: 'MID STAKES',  color: '#d4af37', bg: 'rgba(212,175,55,0.15)' } :
                    { label: 'LOW STAKES',   color: '#38a169', bg: 'rgba(56,161,105,0.15)' };
  return (
    <span
      className="text-xs font-bold px-2 py-0.5 rounded-full tracking-wider"
      style={{ color: tier.color, background: tier.bg, border: `1px solid ${tier.color}40` }}
    >
      {tier.label}
    </span>
  );
};

const Lobby = () => {
  const { user, logout } = useAuth();
  const { rooms, createRoom, joinRoom } = useGame();
  const navigate = useNavigate();
  const { toast } = useToast();

  const [newRoomName, setNewRoomName] = useState('');
  const [minBet, setMinBet] = useState(50);
  const [showCreateModal, setShowCreateModal] = useState(false);

  const handleCreateRoom = () => {
    if (!newRoomName.trim()) {
      toast({ title: 'Room name required', variant: 'destructive' });
      return;
    }
    createRoom(newRoomName.trim(), minBet);
    setNewRoomName('');
    setMinBet(50);
    setShowCreateModal(false);
    toast({ title: 'Table created!', description: 'Your room is ready.' });
  };

  const handleJoinRoom = (roomId: string) => {
    joinRoom(roomId);
    navigate('/game');
  };

  const handleLogout = async () => {
    await logout();
    navigate('/');
  };

  const mockPlayerCounts = [2, 4, 3, 5, 2, 4];

  return (
    <div
      className="min-h-screen"
      style={{ background: 'radial-gradient(ellipse at 50% 0%, #1a0d3a 0%, #0a0618 60%, #000 100%)' }}
    >
      <div className="h-1" style={{ background: 'linear-gradient(90deg, transparent, #d4af37, #f0d060, #d4af37, transparent)' }} />

      {/* Header */}
      <header
        className="sticky top-0 z-30 px-6 py-3 flex items-center justify-between"
        style={{ background: 'rgba(10,6,24,0.88)', backdropFilter: 'blur(12px)', borderBottom: '1px solid rgba(212,175,55,0.15)' }}
      >
        <div className="flex items-center gap-3">
          <span className="text-2xl font-black tracking-wider gold-text" style={{ fontFamily: 'Georgia, serif' }}>TEEN PATTI</span>
          <span className="text-yellow-500/40 text-xs tracking-widest hidden sm:block">PLAYROOM</span>
        </div>
        <div className="flex items-center gap-4">
          {user && (
            <>
              <div className="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-full" style={{ background: 'rgba(212,175,55,0.08)', border: '1px solid rgba(212,175,55,0.2)' }}>
                <ChipBadge amount={user.balance} />
              </div>
              <button onClick={() => navigate('/profile')} className="w-9 h-9 rounded-full overflow-hidden border-2 border-yellow-500/40 hover:border-yellow-400 transition-colors">
                <img src={user.photoURL} alt={user.name} className="w-full h-full object-cover" />
              </button>
              <button onClick={handleLogout} className="p-2 rounded-lg text-white/40 hover:text-white/80 hover:bg-white/5 transition-colors" title="Logout">
                <LogOut size={18} />
              </button>
            </>
          )}
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 py-8">
        <div className="mb-8 fade-in-up">
          <h1 className="text-white text-2xl font-bold mb-1">
            Welcome back, <span className="text-yellow-400">{user?.name?.split(' ')[0]}</span>
          </h1>
          <p className="text-white/40 text-sm">Choose a table and start playing</p>
        </div>

        {/* Stats row */}
        <div className="grid grid-cols-3 gap-4 mb-8">
          {[
            { icon: '🎰', label: 'Tables Live', value: rooms.length },
            { icon: '👥', label: 'Players Online', value: '1,284' },
            { icon: '💰', label: 'Your Balance', value: `₹${user?.balance?.toLocaleString() || 0}` },
          ].map(stat => (
            <div
              key={stat.label}
              className="rounded-xl p-4 flex items-center gap-3"
              style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.07)' }}
            >
              <span className="text-2xl">{stat.icon}</span>
              <div>
                <p className="text-white/40 text-xs">{stat.label}</p>
                <p className="text-white font-bold">{stat.value}</p>
              </div>
            </div>
          ))}
        </div>

        {/* Tables header */}
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-white font-bold text-lg flex items-center gap-2">
            <span className="inline-block w-2 h-2 rounded-full bg-green-400" style={{ boxShadow: '0 0 6px rgba(74,222,128,0.8)' }} />
            Available Tables
          </h2>
          <button
            onClick={() => setShowCreateModal(true)}
            className="flex items-center gap-2 px-4 py-2 rounded-lg font-bold text-black text-sm transition-all active:scale-95"
            style={{ background: 'linear-gradient(135deg, #d4af37 0%, #f0c030 100%)', boxShadow: '0 4px 16px rgba(212,175,55,0.3)' }}
          >
            <Plus size={16} />
            Create Table
          </button>
        </div>

        {/* Table grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {rooms.map((room, idx) => (
            <div
              key={room.id}
              className="lobby-table-card rounded-2xl overflow-hidden"
              style={{ background: 'linear-gradient(135deg, rgba(255,255,255,0.05) 0%, rgba(255,255,255,0.02) 100%)', border: '1px solid rgba(255,255,255,0.08)' }}
            >
              {/* Felt preview */}
              <div className="relative h-32 flex items-center justify-center overflow-hidden" style={{ background: 'radial-gradient(ellipse at center, #1e6b35 0%, #0e3d1e 100%)', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                {/* Mini oval table */}
                <div
                  className="relative flex items-center justify-center"
                  style={{ width: 160, height: 80, background: 'radial-gradient(ellipse, #226b3a 0%, #145025 100%)', borderRadius: '50%', border: '10px solid #3d1f06', boxShadow: '0 0 0 2px #7a4a10, inset 0 0 20px rgba(0,0,0,0.4)' }}
                >
                  {[{ left: '30%', rotate: '-15deg' }, { left: '43%', rotate: '0deg' }, { left: '56%', rotate: '12deg' }].map((c, i) => (
                    <div key={i} className="absolute rounded-sm" style={{ width: 14, height: 20, left: c.left, top: '50%', transform: `translateY(-50%) rotate(${c.rotate})`, background: i % 2 === 0 ? '#1a4b8f' : 'white', boxShadow: '0 2px 4px rgba(0,0,0,0.5)' }} />
                  ))}
                </div>

                <div className="absolute top-3 right-3 flex items-center gap-1 px-2 py-1 rounded-full text-xs font-bold text-white" style={{ background: 'rgba(0,0,0,0.5)', backdropFilter: 'blur(4px)' }}>
                  <Users size={10} />
                  <span>{mockPlayerCounts[idx % mockPlayerCounts.length]}/6</span>
                </div>

                <div className="absolute top-3 left-3 flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full" style={{ background: room.status === 'waiting' ? '#4ade80' : '#f59e0b', boxShadow: room.status === 'waiting' ? '0 0 6px #4ade80' : '0 0 6px #f59e0b' }} />
                  <span className="text-white/70 text-xs">{room.status === 'waiting' ? 'Open' : 'In Progress'}</span>
                </div>
              </div>

              {/* Card body */}
              <div className="p-4">
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <h3 className="text-white font-bold">{room.name}</h3>
                    <StakeBadge minBet={room.minBet} />
                  </div>
                  <ChevronRight size={18} className="text-white/30 mt-1 flex-shrink-0" />
                </div>

                <div className="flex items-center justify-between text-sm">
                  <div className="flex items-center gap-1 text-white/50">
                    <span>Min bet:</span>
                    <span className="text-yellow-400 font-semibold">₹{room.minBet}</span>
                  </div>
                  {room.pot > 0 && (
                    <div className="flex items-center gap-1 text-white/50">
                      <Trophy size={12} />
                      <span className="text-yellow-400 font-semibold">₹{room.pot}</span>
                    </div>
                  )}
                </div>

                <button
                  onClick={() => handleJoinRoom(room.id)}
                  className="w-full mt-4 py-2.5 rounded-lg font-bold text-sm transition-all active:scale-95"
                  style={{
                    background: room.status === 'waiting' ? 'linear-gradient(135deg, #1e6b35 0%, #145025 100%)' : 'rgba(255,255,255,0.06)',
                    border: room.status === 'waiting' ? '1px solid rgba(74,222,128,0.3)' : '1px solid rgba(255,255,255,0.1)',
                    color: room.status === 'waiting' ? '#4ade80' : 'rgba(255,255,255,0.4)',
                  }}
                >
                  {room.status === 'waiting' ? 'Join Table' : 'Spectate'}
                </button>
              </div>
            </div>
          ))}

          {rooms.length === 0 && (
            <div className="col-span-full py-20 text-center">
              <p className="text-white/30 text-lg mb-4">No tables available</p>
              <button onClick={() => setShowCreateModal(true)} className="px-6 py-3 rounded-xl font-bold text-black" style={{ background: 'linear-gradient(135deg, #d4af37 0%, #f0c030 100%)' }}>
                Create the first table
              </button>
            </div>
          )}
        </div>
      </main>

      {/* Create Table Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,0.75)', backdropFilter: 'blur(4px)' }} onClick={e => e.target === e.currentTarget && setShowCreateModal(false)}>
          <div className="w-full max-w-sm rounded-2xl p-6 scale-in" style={{ background: 'linear-gradient(135deg, #1a0d3a 0%, #100820 100%)', border: '1px solid rgba(212,175,55,0.3)', boxShadow: '0 30px 80px rgba(0,0,0,0.7)' }}>
            <h3 className="text-white text-xl font-bold mb-1">Create New Table</h3>
            <p className="text-white/40 text-sm mb-6">Set up your private Teen Patti room</p>

            <div className="space-y-4 mb-6">
              <div>
                <label className="text-white/60 text-xs font-semibold uppercase tracking-wider block mb-2">Table Name</label>
                <Input value={newRoomName} onChange={e => setNewRoomName(e.target.value)} placeholder="e.g. High Rollers Den" className="bg-white/5 border-white/10 text-white placeholder:text-white/20 focus:border-yellow-500/50" onKeyDown={e => e.key === 'Enter' && handleCreateRoom()} />
              </div>

              <div>
                <label className="text-white/60 text-xs font-semibold uppercase tracking-wider block mb-2">Minimum Bet</label>
                <div className="flex gap-2">
                  {[10, 50, 100, 500].map(val => (
                    <button
                      key={val}
                      onClick={() => setMinBet(val)}
                      className="flex-1 py-2 rounded-lg text-sm font-bold transition-all"
                      style={{
                        background: minBet === val ? 'rgba(212,175,55,0.2)' : 'rgba(255,255,255,0.04)',
                        border: minBet === val ? '1px solid rgba(212,175,55,0.5)' : '1px solid rgba(255,255,255,0.08)',
                        color: minBet === val ? '#f0d060' : 'rgba(255,255,255,0.4)',
                      }}
                    >
                      ₹{val}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <div className="flex gap-3">
              <button onClick={() => setShowCreateModal(false)} className="flex-1 py-3 rounded-xl text-white/60 hover:text-white font-semibold transition-colors" style={{ border: '1px solid rgba(255,255,255,0.1)' }}>
                Cancel
              </button>
              <button onClick={handleCreateRoom} className="flex-1 py-3 rounded-xl font-bold text-black transition-all active:scale-95" style={{ background: 'linear-gradient(135deg, #d4af37 0%, #f0c030 100%)', boxShadow: '0 4px 16px rgba(212,175,55,0.3)' }}>
                Create Table
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Lobby;
