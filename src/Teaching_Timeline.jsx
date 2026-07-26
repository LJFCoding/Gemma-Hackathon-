import React, { useEffect, useRef, useState } from 'react';

export default function TeachingTimeline() {
    // ========================================================================
    // 1. YOUR SMART LOGIC & STATE (The "Brains")
    // ========================================================================
    const bottomRef = useRef(null);
    const [isStreaming, setIsStreaming] = useState(false);
    const [totalCount, setTotalCount] = useState(1);

    // Audio & Gemma State
    const [isRecording, setIsRecording] = useState(false);
    const [liveTranscript, setLiveTranscript] = useState("");
    const [feedback, setFeedback] = useState(null);
    const recognitionRef = useRef(null);

    // Learner Profile State
    const [learnerProfile, setLearnerProfile] = useState({
        current_difficulty: "Beginner",
        weak_spots: ["Ratio Fractions"],
        mastery_score: 45
    });

    // Timeline Blocks State
    const [blocks, setBlocks] = useState([
        {
            id: "block_001",
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            topic: "System Check",
            who: "AI SYSTEM",
            transcript: "Welcome to the live session. All systems are initialized and ready.",
            rawSvg: `<svg viewBox="0 0 500 300" xmlns="http://www.w3.org/2000/svg">
                <rect width="100%" height="100%" fill="transparent" rx="10" stroke="#475569" stroke-dasharray="4"/>
                <circle cx="250" cy="150" r="50" fill="#F43F5E" />
                <text x="250" y="230" fill="#ffffff" font-family="sans-serif" font-weight="bold" text-anchor="middle">UI Ready!</text>
               </svg>`
        }
    ]);

    // Scroll to bottom of transcript automatically
    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [blocks, liveTranscript]);

    // (Keep your WebSocket and SpeechRecognition useEffects exactly the same here)
    // ... I am keeping the setup simple so we focus on the UI wiring ...

    const toggleRecording = () => {
        if (isRecording) {
            setIsRecording(false);
            setFeedback({ score: "Pending...", text: "Analyzing answer with Gemma 4..." });
            // WS send logic goes here
        } else {
            setIsRecording(true);
            setLiveTranscript("Listening to student audio...");
        }
    };

    // ========================================================================
    // 2. DEVELOPER 3's UI LAYOUT (The "Beauty" - Wired Up)
    // ========================================================================
    return (
        <>
            {/* Dev 3's Animated Backgrounds */}
            <div className="silk-bg" />
            <div className="grain" />

            {/* Main App Shell */}
            <div className="app-shell">

                {/* Top Navigation Bar */}
                <header className="topbar">
                    <div className="brand">V2V Co-Pilot</div>

                    <div className="control-pill">
                        {/* The Audio Recording Button */}
                        <button
                            onClick={toggleRecording}
                            className={`mic-btn ${isRecording ? 'is-on' : ''}`}
                            title="Answer Verbally"
                        >
                            🎤
                        </button>

                        {/* Dev 3's Waveform Animation (Only animates when recording) */}
                        <div className={`waveform ${!isRecording ? 'is-paused' : ''}`}>
                            <div className="waveform__bar" />
                            <div className="waveform__bar" />
                            <div className="waveform__bar" />
                            <div className="waveform__bar" />
                            <div className="waveform__bar" />
                        </div>

                        {/* Start/Stop Stream Button */}
                        <button
                            onClick={() => setIsStreaming(!isStreaming)}
                            className="pill-btn"
                            style={{ color: isStreaming ? '#F43F5E' : '#10b981' }}
                            title="Toggle AI Stream"
                        >
                            {isStreaming ? '🛑' : '📡'}
                        </button>
                    </div>

                    <div style={{ justifySelf: 'end', color: '#cbd5e1', fontSize: '0.875rem' }}>
                        Score: <strong>{totalCount * 50}</strong> | Mastery: <strong style={{color: '#10b981'}}>{learnerProfile.mastery_score}%</strong>
                    </div>
                </header>

                {/* Main Content Area */}
                <main className="workspace">

                    {/* Left Panel: The Visual Stage (Whiteboard) */}
                    <div className="stage">
                        <div className="frame-stack">
                            <div className="frame frame--back" />
                            <div className="frame frame--mid" />
                            <div className="frame frame--front">
                                {/* Dynamically render the most recent SVG block */}
                                <div
                                    style={{ width: '100%', height: '100%', padding: '1rem' }}
                                    dangerouslySetInnerHTML={{ __html: blocks[blocks.length - 1].rawSvg }}
                                />
                            </div>
                        </div>

                        {/* Live Indicator */}
                        {isStreaming && (
                            <div className="stage__live">
                                <div className="live-dot" /> LIVE STREAM
                            </div>
                        )}
                    </div>

                    {/* Right Panel: The Transcript & Feedback */}
                    <div className="transcript">
                        <div className="transcript__header">Live Transcript</div>

                        <div className="transcript__body">
                            {/* Render Historical Blocks */}
                            {blocks.map((block) => (
                                <div key={block.id} className="line">
                                    <span className="line__who">{block.who || "AI PEDAGOGY"}</span>
                                    <p className="line__text">{block.transcript}</p>
                                </div>
                            ))}

                            {/* Render Student's Live Voice Transcript */}
                            {liveTranscript && (
                                <div className="line" style={{ marginTop: '1rem', borderLeft: '3px solid #10b981', paddingLeft: '1rem' }}>
                                    <span className="line__who" style={{ color: '#10b981' }}>STUDENT (MIC)</span>
                                    <p className="line__text" style={{ fontStyle: 'italic' }}>{liveTranscript}</p>
                                </div>
                            )}

                            {/* Render Gemma's Feedback */}
                            {feedback && (
                                <div className="line glass" style={{ marginTop: '1rem', padding: '1rem', borderRadius: '0.75rem' }}>
                                    <span className="line__who" style={{ color: '#38bdf8' }}>GEMMA 4 FEEDBACK</span>
                                    <p className="line__text">{feedback.text}</p>
                                </div>
                            )}

                            <div ref={bottomRef} />
                        </div>
                    </div>

                </main>
            </div>
        </>
    );
}