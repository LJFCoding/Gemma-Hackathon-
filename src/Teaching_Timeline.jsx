import React, {useEffect, useRef, useState} from 'react';

export default function TeachingTimeline() {
    const bottomRef = useRef(null);

    // Hour 1 Dummy State: A hardcoded block to ensure the SVG injects properly
    const [blocks, setBlocks] = useState([
        {
            id: "block_001",
            timestamp: new Date().toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'}),
            topic: "System Check",
            archetype: "START",
            rawSvg: `<svg viewBox="0 0 500 300" xmlns="http://www.w3.org/2000/svg">
                <rect width="100%" height="100%" fill="#1e1e1e" rx="10" stroke="#374151"/>
                <circle cx="250" cy="150" r="50" fill="#6366f1" />
                <text x="250" y="230" fill="#ffffff" font-family="sans-serif" font-weight="bold" text-anchor="middle">UI Ready!</text>
               </svg>`
        }
    ]);

    // The Auto-Scroll Hook (Crucial for the "Infinite Whiteboard" feel)
    useEffect(() => {
        bottomRef.current?.scrollIntoView({behavior: 'smooth'});
    }, [blocks]);

    // Dev button function to simulate Dev 1 (Backend) sending a new block
    const simulateNewBlock = () => {
        const newBlock = {
            id: `block_${Date.now()}`,
            timestamp: new Date().toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'}),
            topic: "New Ratio Prompt",
            archetype: "RATIO_POUCH",
            rawSvg: `<svg viewBox="0 0 500 300" xmlns="http://www.w3.org/2000/svg">
                <rect width="100%" height="100%" fill="#121212" rx="10" stroke="#374151"/>
                <circle cx="200" cy="150" r="30" fill="#e53935" data-trigger="token" data-tag-color="red" />
                <circle cx="300" cy="150" r="30" fill="#1e88e5" data-trigger="token" data-tag-color="blue" />
               </svg>`
        };
        setBlocks(prev => [...prev, newBlock]);
    };

    return (
        <div className="flex h-screen bg-black overflow-hidden font-sans">

            {/* Main Whiteboard Canvas */}
            <div className="flex-1 overflow-y-auto p-8 flex flex-col gap-12 scroll-smooth">

                {/* Header / Gamification Bar */}
                <div
                    className="sticky top-0 z-10 flex justify-between items-center bg-black/80 backdrop-blur-md pb-4 border-b border-gray-800">
                    <h1 className="text-xl text-white font-bold tracking-wide">V2V <span
                        className="text-indigo-500">Co-Pilot</span></h1>
                    <div className="flex gap-4">
                        <span className="text-gray-400 font-mono text-sm border border-gray-800 px-3 py-1 rounded-full">🗼 Tower: {blocks.length}</span>
                        <span
                            className="text-emerald-400 font-mono text-sm border border-emerald-900/50 bg-emerald-900/20 px-3 py-1 rounded-full">Score: {blocks.length * 50}</span>
                    </div>
                </div>

                {/* Timeline Blocks */}
                {blocks.map((block) => (
                    <div key={block.id}
                         className="w-full max-w-4xl mx-auto bg-[#1a1a1a] border border-gray-800 rounded-2xl p-6 shadow-2xl transition-all duration-300 hover:border-gray-700">

                        {/* Block Metadata */}
                        <div className="flex justify-between items-center border-b border-gray-800/50 pb-4 mb-4">
                            <div className="flex items-center gap-3">
                <span
                    className="px-2 py-1 bg-indigo-500/10 text-indigo-400 text-xs font-mono rounded border border-indigo-500/20">
                  {block.archetype}
                </span>
                                <h3 className="text-gray-200 font-medium">{block.topic}</h3>
                            </div>
                            <span className="text-gray-500 text-xs font-mono">{block.timestamp}</span>
                        </div>

                        {/* SVG Injection Container */}
                        <div
                            className="w-full flex justify-center items-center bg-black rounded-xl overflow-hidden"
                            dangerouslySetInnerHTML={{__html: block.rawSvg}}
                        />
                    </div>
                ))}

                {/* Invisible div targeted by the scroll hook */}
                <div ref={bottomRef} className="h-4"/>
            </div>

            {/* Dev Tools Sidebar (For Hour 1 Testing) */}
            <div className="w-64 bg-gray-900 border-l border-gray-800 p-4 flex flex-col gap-4">
                <h3 className="text-gray-400 text-sm uppercase tracking-wider font-bold mb-2">Dev Tools</h3>
                <button
                    onClick={simulateNewBlock}
                    className="bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg py-2 px-4 text-sm font-medium transition-colors"
                >
                    + Add SVG Block
                </button>
            </div>

        </div>
    );
}