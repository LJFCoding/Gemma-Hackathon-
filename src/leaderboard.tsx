import React from 'react';

export default function Leaderboard() {
    return (
        <div className="app-shell" style={{ padding: '2rem', maxWidth: '800px', margin: '0 auto' }}>

            {/* Background Effects */}
            <div className="silk-bg"></div>
            <div className="grain"></div>

            {/* Header */}
            <header style={{ textAlign: 'center', marginBottom: '2rem' }}>
                <h1 className="brand" style={{ fontSize: '2.5rem', marginBottom: '0.5rem' }}>🏆 V2V Leaderboard</h1>
                <p style={{ color: '#cbd5e1' }}>Top students mastering concepts through real-time voice and visuals.</p>
            </header>

            {/* Leaderboard Card Container */}
            <div className="transcript" style={{ padding: '1.5rem' }}>
                <div className="transcript__header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span>Rankings</span>
                    <span style={{ fontSize: '1rem', color: '#38bdf8' }}>Tower Score</span>
                </div>

                <div className="transcript__body" style={{ gap: '1rem' }}>

                    {/* Rank 1 */}
                    <div className="glass" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '1rem', borderRadius: '0.75rem' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                            <span style={{ fontSize: '1.25rem', fontWeight: 'bold', color: '#facc15' }}>1</span>
                            <div>
                                <strong style={{ color: '#f1f5f9' }}>Alex Chen</strong>
                                <p style={{ fontSize: '0.85rem', color: '#94a3b8' }}>Level: Advanced</p>
                            </div>
                        </div>
                        <span style={{ fontFamily: 'monospace', color: '#34d399', fontWeight: 'bold' }}>4,950 pts</span>
                    </div>

                    {/* Rank 2 */}
                    <div className="glass" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '1rem', borderRadius: '0.75rem' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                            <span style={{ fontSize: '1.25rem', fontWeight: 'bold', color: '#cbd5e1' }}>2</span>
                            <div>
                                <strong style={{ color: '#f1f5f9' }}>Sarah Jenkins</strong>
                                <p style={{ fontSize: '0.85rem', color: '#94a3b8' }}>Level: Intermediate</p>
                            </div>
                        </div>
                        <span style={{ fontFamily: 'monospace', color: '#34d399', fontWeight: 'bold' }}>4,400 pts</span>
                    </div>

                    {/* Rank 3 */}
                    <div className="glass" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '1rem', borderRadius: '0.75rem' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                            <span style={{ fontSize: '1.25rem', fontWeight: 'bold', color: '#fb923c' }}>3</span>
                            <div>
                                <strong style={{ color: '#f1f5f9' }}>Marcus Vance</strong>
                                <p style={{ fontSize: '0.85rem', color: '#94a3b8' }}>Level: Intermediate</p>
                            </div>
                        </div>
                        <span style={{ fontFamily: 'monospace', color: '#34d399', fontWeight: 'bold' }}>3,850 pts</span>
                    </div>

                </div>
            </div>

        </div>
    );
}