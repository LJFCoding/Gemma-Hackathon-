// 🔌 REAL WEBSOCKET CONNECTION (Hour 3)
useEffect(() => {
    // Connect to Dev 1's backend WebSocket server (change port/url as agreed with your team)
    const ws = new WebSocket('ws://localhost:8000/ws/stream');

    ws.onopen = () => {
        console.log("Connected to V2V Backend WebSocket!");
    };

    ws.onmessage = (event) => {
        try {
            const payload = JSON.parse(event.data);

            // 1. Handle Visual SVG / Timeline Block Updates
            if (payload.type === "NEW_BLOCK") {
                setTotalCount(prev => prev + 1);
                setBlocks(prev => [...prev.slice(-5), payload.block]);
            }

            // 2. Handle Zero-Latency DOM Patches (Gemma 4 mutations)
            if (payload.type === "DOM_PATCH") {
                applyDomPatch(payload.instruction);
            }

            // 3. Handle Live Learner Profile Updates
            if (payload.type === "PROFILE_UPDATE") {
                setLearnerProfile(payload.profile);
            }

        } catch (err) {
            console.error("Failed to parse incoming WebSocket payload:", err);
        }
    };

    ws.onerror = (error) => {
        console.error("WebSocket error observed:", error);
    };

    // Cleanup connection on component unmount
    return () => {
        ws.close();
    };
}, []);