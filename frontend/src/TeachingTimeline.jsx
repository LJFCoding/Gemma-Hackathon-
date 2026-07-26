import React, { useCallback, useEffect, useRef, useState } from 'react';

/**
 * V2V Co-Pilot — live teaching timeline with Gemma-graded verbal assessment.
 *
 * Voice pipeline:
 *   mic → Web Speech API (browser STT) → WS TEXT_ANSWER → Gemma 4 → GRADE_RESULT → spoken feedback
 *
 * The transcript is produced in the browser on purpose: Gemma has no audio
 * input modality ("Audio input modality is not enabled for this model"), so
 * sending raw audio to the backend cannot be graded.
 */

const WS_URL = import.meta.env?.VITE_WS_URL ?? 'ws://localhost:8000/ws/stream';

/* ------------------------------------------------------------------ */
/* Learner profile                                                     */
/* ------------------------------------------------------------------ */
function LearnerProfilePanel({ profile }) {
    return (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 flex flex-col gap-3 text-white">
            <div className="flex justify-between items-center border-b border-gray-800 pb-2">
                <h3 className="text-xs font-bold tracking-wider uppercase text-indigo-400">Learner DNA Profile</h3>
                <span className="text-xs font-mono bg-indigo-950 text-indigo-300 px-2 py-0.5 rounded border border-indigo-800">
                    Level: {profile.current_difficulty}
                </span>
            </div>

            <div className="flex flex-col gap-1">
                <div className="flex justify-between text-xs text-gray-400">
                    <span>Mastery Progress</span>
                    <span className="text-emerald-400 font-mono">{profile.mastery_score}%</span>
                </div>
                <div className="w-full bg-gray-800 h-2 rounded-full overflow-hidden">
                    <div
                        className="bg-emerald-500 h-full transition-all duration-500"
                        style={{ width: `${profile.mastery_score}%` }}
                    />
                </div>
            </div>

            <div className="flex flex-col gap-1.5">
                <span className="text-xs text-gray-400 font-medium">Identified Weak Spots:</span>
                <div className="flex flex-wrap gap-1.5">
                    {profile.weak_spots.length === 0 && (
                        <span className="text-xs text-gray-600 italic">None yet</span>
                    )}
                    {profile.weak_spots.map((spot, index) => (
                        <span
                            key={index}
                            className="px-2 py-0.5 bg-rose-500/10 text-rose-400 text-xs font-mono rounded-md border border-rose-500/20"
                        >
                            {spot}
                        </span>
                    ))}
                </div>
            </div>
        </div>
    );
}

/* ------------------------------------------------------------------ */
/* Verbal assessment — browser STT + Gemma grading                     */
/* ------------------------------------------------------------------ */
function VoiceAnswerModule({ send, connected, topic, feedback, pending, onTranscript }) {
    const [isRecording, setIsRecording] = useState(false);
    const [interim, setInterim] = useState('');
    const [error, setError] = useState(null);
    const recognitionRef = useRef(null);
    const [typed, setTyped] = useState('');

    const SR = typeof window !== 'undefined'
        ? window.SpeechRecognition || window.webkitSpeechRecognition
        : null;

    useEffect(() => {
        if (!SR) return;

        const recognition = new SR();
        recognition.lang = 'en-US';
        recognition.continuous = false;
        recognition.interimResults = true;
        recognition.maxAlternatives = 1;

        recognition.onstart = () => { setIsRecording(true); setError(null); setInterim(''); };

        recognition.onresult = (event) => {
            let finalText = '';
            let partial = '';
            for (let i = event.resultIndex; i < event.results.length; i += 1) {
                const chunk = event.results[i][0].transcript;
                if (event.results[i].isFinal) finalText += chunk;
                else partial += chunk;
            }
            setInterim(partial);
            if (finalText.trim()) {
                onTranscript(finalText.trim());
                setInterim('');
            }
        };

        recognition.onerror = (event) => {
            setError(
                event.error === 'not-allowed'
                    ? 'Microphone permission denied.'
                    : event.error === 'no-speech'
                        ? "Didn't catch that — try again."
                        : `Speech error: ${event.error}`
            );
        };

        recognition.onend = () => { setIsRecording(false); setInterim(''); };

        recognitionRef.current = recognition;
        return () => { recognition.onend = null; recognition.abort(); };
    }, [SR, onTranscript]);

    const toggle = () => {
        const recognition = recognitionRef.current;
        if (!recognition || pending) return;
        if (isRecording) recognition.stop();
        else recognition.start();
    };

    const submitTyped = (event) => {
        event.preventDefault();
        const value = typed.trim();
        if (!value || pending) return;
        setTyped('');
        onTranscript(value);
    };

    return (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 flex flex-col gap-3 text-white">
            <div className="flex justify-between items-center border-b border-gray-800 pb-2">
                <h3 className="text-xs font-bold uppercase tracking-wider text-indigo-400">Verbal QA Assessment</h3>
                <span className={`text-xs font-mono ${connected ? 'text-emerald-400' : 'text-rose-400'}`}>
                    {connected ? 'Gemma live' : 'offline'}
                </span>
            </div>

            <p className="text-xs text-gray-500">
                Topic: <span className="text-gray-300">{topic}</span>
            </p>

            {SR ? (
                <button
                    onClick={toggle}
                    disabled={pending || !connected}
                    className={`${
                        isRecording ? 'bg-rose-600 animate-pulse' : 'bg-indigo-600 hover:bg-indigo-500'
                    } disabled:bg-gray-700 disabled:cursor-not-allowed text-white rounded-lg py-2 px-4 text-xs font-medium transition-colors`}
                >
                    {pending ? 'Gemma is grading…' : isRecording ? 'Stop & Submit Answer' : 'Answer Verbally'}
                </button>
            ) : (
                <form onSubmit={submitTyped} className="flex gap-2">
                    <input
                        value={typed}
                        onChange={(e) => setTyped(e.target.value)}
                        placeholder="Speech unsupported — type your answer"
                        className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-xs text-white"
                    />
                    <button className="bg-indigo-600 hover:bg-indigo-500 rounded-lg px-3 py-2 text-xs font-medium">
                        Send
                    </button>
                </form>
            )}

            {interim && <p className="text-xs text-gray-500 italic">“{interim}”</p>}
            {error && <p className="text-xs text-rose-400">{error}</p>}

            {feedback && (
                <div className="bg-emerald-950/40 border border-emerald-900/50 p-3 rounded-lg text-xs flex flex-col gap-1">
                    <span className="text-emerald-400 font-bold font-mono">Result: {feedback.score}</span>
                    {feedback.transcript && (
                        <p className="text-gray-500 italic">You said: “{feedback.transcript}”</p>
                    )}
                    <p className="text-gray-300 leading-relaxed">{feedback.text}</p>
                </div>
            )}
        </div>
    );
}

/* ------------------------------------------------------------------ */
/* Main timeline                                                       */
/* ------------------------------------------------------------------ */
export default function TeachingTimeline() {
    const bottomRef = useRef(null);
    const wsRef = useRef(null);

    const [connected, setConnected] = useState(false);
    const [isStreaming, setIsStreaming] = useState(false);
    const [totalCount, setTotalCount] = useState(1);
    const [feedback, setFeedback] = useState(null);
    const [pending, setPending] = useState(false);
    const [muted, setMuted] = useState(false);

    const [learnerProfile, setLearnerProfile] = useState({
        current_difficulty: 'Beginner',
        weak_spots: ['Ratio Fractions'],
        mastery_score: 45,
    });

    const [blocks, setBlocks] = useState([
        {
            id: 'block_001',
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            topic: 'System Check',
            archetype: 'START',
            transcript: 'Welcome to the live session. All systems are initialized and ready.',
            rawSvg: `<svg viewBox="0 0 500 300" xmlns="http://www.w3.org/2000/svg">
                <rect width="100%" height="100%" fill="#1e1e1e" rx="10" stroke="#374151"/>
                <circle cx="250" cy="150" r="50" fill="#6366f1" />
                <text x="250" y="230" fill="#ffffff" font-family="sans-serif" font-weight="bold" text-anchor="middle">UI Ready!</text>
               </svg>`,
        },
    ]);

    const currentTopic = blocks[blocks.length - 1]?.topic ?? 'the current topic';

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [blocks]);

    /* ---- DOM patching (declared before the socket effect that uses it) ---- */
    const applyDomPatch = useCallback((patchInstruction) => {
        if (patchInstruction?.protocol_action !== 'UPDATE_TAG') return;

        let selector = `[data-trigger="${patchInstruction.target_trigger}"]`;
        if (patchInstruction.filter) {
            Object.entries(patchInstruction.filter).forEach(([key, value]) => {
                selector += `[${key}="${value}"]`;
            });
        }

        document.querySelectorAll(selector).forEach((el) => {
            Object.entries(patchInstruction.mutations ?? {}).forEach(([attrName, attrValue]) => {
                el.setAttribute(attrName, attrValue);
            });
        });
    }, []);

    /* ---- Speak Gemma's feedback aloud ---- */
    const speak = useCallback((text) => {
        if (muted || !text || typeof window === 'undefined' || !window.speechSynthesis) return;
        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = 'en-US';
        window.speechSynthesis.speak(utterance);
    }, [muted]);

    /* ---- WebSocket ---- */
    useEffect(() => {
        let ws;
        try {
            ws = new WebSocket(WS_URL);
        } catch {
            return undefined;
        }
        wsRef.current = ws;

        ws.onopen = () => setConnected(true);
        ws.onclose = () => setConnected(false);
        ws.onerror = () => setConnected(false);

        ws.onmessage = (event) => {
            let payload;
            try {
                payload = JSON.parse(event.data);
            } catch (err) {
                console.error('Failed to parse incoming WebSocket payload:', err);
                return;
            }

            switch (payload.type) {
                case 'NEW_BLOCK':
                    setTotalCount((prev) => prev + 1);
                    setBlocks((prev) => [...prev, payload.block].slice(-6));
                    break;

                case 'DOM_PATCH':
                    applyDomPatch(payload.instruction);
                    break;

                case 'PROFILE_UPDATE':
                    setLearnerProfile(payload.profile);
                    break;

                case 'GRADE_RESULT': {
                    setPending(false);
                    setFeedback({
                        score: payload.score,
                        text: payload.text,
                        transcript: payload.transcript,
                    });
                    speak(payload.text);

                    // Gemma drives the learner profile — no more hardcoded values.
                    setLearnerProfile((prev) => ({
                        current_difficulty: payload.difficulty ?? prev.current_difficulty,
                        weak_spots: payload.weak_spot
                            ? Array.from(new Set([...prev.weak_spots, payload.weak_spot])).slice(-3)
                            : prev.weak_spots,
                        mastery_score: Math.max(
                            0,
                            Math.min(100, prev.mastery_score + (payload.mastery_delta ?? 0)),
                        ),
                    }));
                    break;
                }

                case 'ASSISTANT_REPLY':
                    setPending(false);
                    speak(payload.reply);
                    break;

                case 'ERROR':
                    setPending(false);
                    setFeedback({ score: '—', text: payload.detail });
                    break;

                default:
                    break;
            }
        };

        return () => {
            ws.onclose = null;
            ws.close();
        };
    }, [applyDomPatch, speak]);

    const send = useCallback((payload) => {
        const ws = wsRef.current;
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify(payload));
            return true;
        }
        return false;
    }, []);

    /* ---- Submit a spoken answer for grading ---- */
    const handleTranscript = useCallback((transcript) => {
        setFeedback(null);
        setPending(true);
        const ok = send({
            type: 'TEXT_ANSWER',
            student_id: 'user_123',
            topic: currentTopic,
            transcript,
        });
        if (!ok) {
            setPending(false);
            setFeedback({ score: '—', text: 'Not connected to the backend. Is uvicorn running?' });
        }
    }, [send, currentTopic]);

    /* ---- Local simulation fallback ---- */
    useEffect(() => {
        if (!isStreaming) return undefined;

        const interval = setInterval(() => {
            const sampleData = [
                { topic: 'Ratio Analysis', text: 'Notice how the red token shifts position relative to the blue benchmark.' },
                { topic: 'Market Penetration', text: 'This vector calculates our core growth trajectory over the next quarter.' },
                { topic: 'Cost Breakdown', text: 'We isolate the variables to optimize performance metrics instantly.' },
            ];
            const item = sampleData[Math.floor(Math.random() * sampleData.length)];

            setTotalCount((prev) => prev + 1);
            setBlocks((prev) => [...prev, {
                id: `block_${Date.now()}`,
                timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
                topic: item.topic,
                archetype: 'STREAM_DATA',
                transcript: item.text,
                rawSvg: `<svg viewBox="0 0 500 300" xmlns="http://www.w3.org/2000/svg">
                    <rect width="100%" height="100%" fill="#121212" rx="10" stroke="#374151"/>
                    <circle cx="200" cy="150" r="30" fill="#e53935" data-trigger="token" data-tag-color="red" />
                    <circle cx="300" cy="150" r="30" fill="#1e88e5" data-trigger="token" data-tag-color="blue" />
                    <text x="250" y="60" fill="#9ca3af" font-family="sans-serif" font-size="14" text-anchor="middle">Live Transcript Synced</text>
                   </svg>`,
            }].slice(-6));
        }, 3000);

        return () => clearInterval(interval);
    }, [isStreaming]);

    const simulateNewBlock = () => {
        setTotalCount((prev) => prev + 1);
        setBlocks((prev) => [...prev, {
            id: `block_${Date.now()}`,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            topic: 'New Ratio Prompt',
            archetype: 'RATIO_POUCH',
            transcript: 'User manually injected a new visual prompt block into the timeline.',
            rawSvg: `<svg viewBox="0 0 500 300" xmlns="http://www.w3.org/2000/svg">
                <rect width="100%" height="100%" fill="#121212" rx="10" stroke="#374151"/>
                <circle cx="200" cy="150" r="30" fill="#e53935" data-trigger="token" data-tag-color="red" />
                <circle cx="300" cy="150" r="30" fill="#1e88e5" data-trigger="token" data-tag-color="blue" />
               </svg>`,
        }].slice(-6));
    };

    const testColorChange = () => {
        applyDomPatch({
            protocol_action: 'UPDATE_TAG',
            target_trigger: 'token',
            filter: { 'data-tag-color': 'red' },
            mutations: { fill: '#facc15', 'data-tag-color': 'yellow' },
        });
    };

    return (
        <div className="flex h-screen bg-black overflow-hidden font-sans">

            {/* Left: whiteboard canvas */}
            <div className="flex-1 flex flex-col h-full border-r border-gray-800">
                <div className="flex justify-between items-center bg-black/80 backdrop-blur-md px-8 py-4 border-b border-gray-800">
                    <h1 className="text-xl text-white font-bold tracking-wide">
                        V2V <span className="text-indigo-500">Co-Pilot</span>
                    </h1>
                    <div className="flex gap-4 items-center">
                        <span className={`text-xs font-mono px-3 py-1 rounded-full border ${
                            connected
                                ? 'text-emerald-400 border-emerald-900/50 bg-emerald-900/20'
                                : 'text-rose-400 border-rose-900/50 bg-rose-900/20'
                        }`}>
                            {connected ? 'Backend connected' : 'Backend offline'}
                        </span>
                        <span className="text-gray-400 font-mono text-sm border border-gray-800 px-3 py-1 rounded-full">
                            Tower: {totalCount}
                        </span>
                        <span className="text-emerald-400 font-mono text-sm border border-emerald-900/50 bg-emerald-900/20 px-3 py-1 rounded-full">
                            Score: {totalCount * 50}
                        </span>
                    </div>
                </div>

                <div className="flex-1 overflow-y-auto p-8 flex flex-col gap-12 scroll-smooth">
                    {blocks.map((block) => (
                        <div
                            key={block.id}
                            className="w-full max-w-4xl mx-auto bg-[#1a1a1a] border border-gray-800 rounded-2xl p-6 shadow-2xl transition-all duration-300 hover:border-gray-700"
                        >
                            <div className="flex justify-between items-center border-b border-gray-800/50 pb-4 mb-4">
                                <div className="flex items-center gap-3">
                                    <span className="px-2 py-1 bg-indigo-500/10 text-indigo-400 text-xs font-mono rounded border border-indigo-500/20">
                                        {block.archetype}
                                    </span>
                                    <h3 className="text-gray-200 font-medium">{block.topic}</h3>
                                </div>
                                <span className="text-gray-500 text-xs font-mono">{block.timestamp}</span>
                            </div>
                            <div
                                className="w-full flex justify-center items-center bg-black rounded-xl overflow-hidden"
                                dangerouslySetInnerHTML={{ __html: block.rawSvg }}
                            />
                        </div>
                    ))}
                    <div ref={bottomRef} className="h-4" />
                </div>
            </div>

            {/* Right: profile, voice QA, transcript, dev tools */}
            <div className="w-96 bg-gray-900 border-l border-gray-800 flex flex-col h-full">
                <div className="p-4 border-b border-gray-800 flex flex-col gap-4">
                    <LearnerProfilePanel profile={learnerProfile} />
                    <VoiceAnswerModule
                        send={send}
                        connected={connected}
                        topic={currentTopic}
                        feedback={feedback}
                        pending={pending}
                        onTranscript={handleTranscript}
                    />
                </div>

                <div className="px-4 py-3 border-b border-gray-800 flex justify-between items-center bg-gray-950/50">
                    <h3 className="text-gray-300 text-xs font-bold uppercase tracking-wider flex items-center gap-2">
                        <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                        Live Transcript
                    </h3>
                    <span className="text-xs text-gray-500 font-mono">STT Stream</span>
                </div>

                <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-3">
                    {blocks.map((block) => (
                        <div
                            key={`transcript_${block.id}`}
                            className="bg-gray-800/40 border border-gray-800 rounded-xl p-3 text-sm flex flex-col gap-1"
                        >
                            <div className="flex justify-between items-center text-xs text-gray-400 font-mono">
                                <span className="text-indigo-400">{block.topic}</span>
                                <span>{block.timestamp}</span>
                            </div>
                            <p className="text-gray-300 leading-relaxed">{block.transcript}</p>
                        </div>
                    ))}
                </div>

                <div className="p-4 bg-gray-950 border-t border-gray-800 flex flex-col gap-2.5">
                    <h3 className="text-gray-400 text-xs uppercase tracking-wider font-bold">Dev Tools</h3>
                    <button
                        onClick={simulateNewBlock}
                        className="bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg py-2 px-4 text-xs font-medium transition-colors"
                    >
                        + Add SVG Block
                    </button>
                    <button
                        onClick={() => setIsStreaming(!isStreaming)}
                        className={`${
                            isStreaming ? 'bg-rose-600 hover:bg-rose-500' : 'bg-emerald-600 hover:bg-emerald-500'
                        } text-white rounded-lg py-2 px-4 text-xs font-bold transition-colors`}
                    >
                        {isStreaming ? 'Stop Stream' : 'Start Live Stream'}
                    </button>
                    <button
                        onClick={testColorChange}
                        className="bg-amber-500 hover:bg-amber-400 text-gray-900 rounded-lg py-2 px-4 text-xs font-bold transition-colors"
                    >
                        Test DOM Patch
                    </button>
                    <button
                        onClick={() => setMuted((m) => !m)}
                        className="bg-gray-700 hover:bg-gray-600 text-white rounded-lg py-2 px-4 text-xs font-medium transition-colors"
                    >
                        {muted ? 'Unmute Gemma' : 'Mute Gemma'}
                    </button>
                </div>
            </div>
        </div>
    );
}
