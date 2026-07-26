import React, { useEffect, useRef, useState } from 'react';

export default function TeachingTimeline() {
    const bottomRef = useRef(null);
    const [isStreaming, setIsStreaming] = useState(false);

    // Track total blocks received infinitely for the score/tower counters
    const [totalCount, setTotalCount] = useState(1);

    // Visual blocks state (capped at 6 for smooth DOM performance)
    const [blocks, setBlocks] = useState([
        {
            id: "block_001",
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            topic: "System Check",
            archetype: "START",
            transcript: "Welcome to the live session. All systems are initialized and ready.",
            rawSvg: `<svg viewBox="0 0 500 300" xmlns="http://www.w3.org/2000/svg">
                <rect width="100%" height="100%" fill="#1e1e1e" rx="10" stroke="#374151"/>
                <circle cx="250" cy="150" r="50" fill="#6366f1" />
                <text x="250" y="230" fill="#ffffff" font-family="sans-serif" font-weight="bold" text-anchor="middle">UI Ready!</text>
               </svg>`
        }
    ]);

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [blocks]);

    // Mock Live Stream Loop with Infinite Score Tracking
    useEffect(() => {
        let interval;
        if (isStreaming) {
            interval = setInterval(() => {
                const sampleData = [
                    { topic: "Ratio Analysis", text: "Notice how the red token shifts position relative to the blue benchmark." },
                    { topic: "Market Penetration", text: "This vector calculates our core growth trajectory over the next quarter." },
                    { topic: "Cost Breakdown", text: "We isolate the variables to optimize performance metrics instantly." }
                ];
                const randomItem = sampleData[Math.floor(Math.random() * sampleData.length)];

                const newBlock = {
                    id: `block_${Date.now()}`,
                    timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
                    topic: randomItem.topic,
                    archetype: "STREAM_DATA",
                    transcript: randomItem.text,
                    rawSvg: `<svg viewBox="0 0 500 300" xmlns="http://www.w3.org/2000/svg">
                    <rect width="100%" height="100%" fill="#121212" rx="10" stroke="#374151"/>
                    <circle cx="200" cy="150" r="30" fill="#e53935" data-trigger="token" data-tag-color="red" />
                    <circle cx="300" cy="150" r="30" fill="#1e88e5" data-trigger="token" data-tag-color="blue" />
                    <text x="250" y="60" fill="#9ca3af" font-family="sans-serif" font-size="14" text-anchor="middle">Live Transcript Synced</text>
                   </svg>`
                };

                // Increment the absolute counter infinitely
                setTotalCount(prev => prev + 1);
                // Keep DOM light by keeping only the last 5 visible blocks
                setBlocks(prev => [...prev.slice(-5), newBlock]);
            }, 3000);
        }
        return () => clearInterval(interval);
    }, [isStreaming]);

    const simulateNewBlock = () => {
        const newBlock = {
            id: `block_${Date.now()}`,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            topic: "New Ratio Prompt",
            archetype: "RATIO_POUCH",
            transcript: "User manually injected a new visual prompt block into the timeline.",
            rawSvg: `<svg viewBox="0 0 500 300" xmlns="http://www.w3.org/2000/svg">
                <rect width="100%" height="100%" fill="#121212" rx="10" stroke="#374151"/>
                <circle cx="200" cy="150" r="30" fill="#e53935" data-trigger="token" data-tag-color="red" />
                <circle cx="300" cy="150" r="30" fill="#1e88e5" data-trigger="token" data-tag-color="blue" />
               </svg>`
        };
        setTotalCount(prev => prev + 1);
        setBlocks(prev => [...prev.slice(-5), newBlock]);
    };

    const applyDomPatch = (patchInstruction) => {
        if (patchInstruction.protocol_action !== "UPDATE_TAG") return;

        let selector = `[data-trigger="${patchInstruction.target_trigger}"]`;
        if (patchInstruction.filter) {
            Object.entries(patchInstruction.filter).forEach(([key, value]) => {
                selector += `[${key}="${value}"]`;
            });
        }

        const targetElements = document.querySelectorAll(selector);
        targetElements.forEach((el) => {
            Object.entries(patchInstruction.mutations).forEach(([attrName, attrValue]) => {
                el.setAttribute(attrName, attrValue);
            });
        });
    };

    const testColorChange = () => {
        const mockPayload = {
            protocol_action: "UPDATE_TAG",
            target_trigger: "token",
            filter: { "data-tag-color": "red" },
            mutations: {
                "fill": "#facc15",
                "data-tag-color": "yellow"
            }
        };
        applyDomPatch(mockPayload);
    };

    return (
        <div className="flex h-screen bg-black overflow-hidden font-sans">

            {/* Left Area: Main Whiteboard Canvas */}
            <div className="flex-1 flex flex-col h-full border-r border-gray-800">

                {/* Header / Gamification Bar (Powered by infinite totalCount) */}
                <div className="flex justify-between items-center bg-black/80 backdrop-blur-md px-8 py-4 border-b border-gray-800">
                    <h1 className="text-xl text-white font-bold tracking-wide">V2V <span className="text-indigo-500">Co-Pilot</span></h1>
                    <div className="flex gap-4">
                        <span className="text-gray-400 font-mono text-sm border border-gray-800 px-3 py-1 rounded-full">🗼 Tower: {totalCount}</span>
                        <span className="text-emerald-400 font-mono text-sm border border-emerald-900/50 bg-emerald-900/20 px-3 py-1 rounded-full">Score: {totalCount * 50}</span>
                    </div>
                </div>

                {/* Scrollable Timeline */}
                <div className="flex-1 overflow-y-auto p-8 flex flex-col gap-12 scroll-smooth">
                    {blocks.map((block) => (
                        <div key={block.id} className="w-full max-w-4xl mx-auto bg-[#1a1a1a] border border-gray-800 rounded-2xl p-6 shadow-2xl transition-all duration-300 hover:border-gray-700">
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

            {/* Right Sidebar: Live Transcript Ticker & Dev Tools */}
            <div className="w-96 bg-gray-900 border-l border-gray-800 flex flex-col h-full">

                {/* Transcript Panel Header */}
                <div className="p-4 border-b border-gray-800 flex justify-between items-center bg-gray-950/50">
                    <h3 className="text-gray-300 text-sm font-bold uppercase tracking-wider flex items-center gap-2">
                        <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
                        Live Transcript
                    </h3>
                    <span className="text-xs text-gray-500 font-mono">STT Stream</span>
                </div>

                {/* Scrollable Transcript List */}
                <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-4">
                    {blocks.map((block) => (
                        <div key={`transcript_${block.id}`} className="bg-gray-800/40 border border-gray-800 rounded-xl p-3 text-sm flex flex-col gap-1">
                            <div className="flex justify-between items-center text-xs text-gray-400 font-mono">
                                <span className="text-indigo-400">{block.topic}</span>
                                <span>{block.timestamp}</span>
                            </div>
                            <p className="text-gray-300 leading-relaxed">{block.transcript}</p>
                        </div>
                    ))}
                </div>

                {/* Dev Tools Footer */}
                <div className="p-4 bg-gray-950 border-t border-gray-800 flex flex-col gap-3">
                    <h3 className="text-gray-400 text-xs uppercase tracking-wider font-bold">Dev Tools</h3>
                    <button
                        onClick={simulateNewBlock}
                        className="bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg py-2 px-4 text-xs font-medium transition-colors"
                    >
                        + Add SVG Block
                    </button>
                    <button
                        onClick={() => setIsStreaming(!isStreaming)}
                        className={`${isStreaming ? 'bg-rose-600 hover:bg-rose-500' : 'bg-emerald-600 hover:bg-emerald-500'} text-white rounded-lg py-2 px-4 text-xs font-bold transition-colors`}
                    >
                        {isStreaming ? '🛑 Stop Stream' : '📡 Start Live Stream'}
                    </button>
                    <button
                        onClick={testColorChange}
                        className="bg-amber-500 hover:bg-amber-400 text-gray-900 rounded-lg py-2 px-4 text-xs font-bold transition-colors"
                    >
                        ⚡ Test DOM Patch
                    </button>
                </div>

            </div>

        </div>
    );
}