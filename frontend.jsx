const { useState, useEffect, useRef, useCallback } = React;

const API = window.BACKEND_URL || "http://localhost:8000";
const WS_BASE = window.BACKEND_URL ? window.BACKEND_URL.replace(/^http/, "ws") : "ws://localhost:8000";

// --- LandingPage ---
function LandingPage({ onHostGame, onJoinGame }) {
  const [joinCode, setJoinCode] = useState("");
  const [joinName, setJoinName] = useState("");
  const [error, setError] = useState("");
  const [serverStatus, setServerStatus] = useState("checking"); // "checking" | "waking" | "online"

  useEffect(() => {
    let isMounted = true;
    let timer = null;

    const checkServer = async (attempt = 1) => {
      try {
        const res = await fetch(`${API}/health`, { method: "GET" });
        if (res.ok && isMounted) {
          setServerStatus("online");
          return;
        }
      } catch (err) {
        // Server might be sleeping on free tier
      }

      if (isMounted) {
        if (attempt >= 2) {
          setServerStatus("waking");
        }
        // Poll every 3 seconds to keep waking the server up
        timer = setTimeout(() => checkServer(attempt + 1), 3000);
      }
    };

    checkServer();
    return () => {
      isMounted = false;
      if (timer) clearTimeout(timer);
    };
  }, []);

  const handleJoin = async () => {
    if (!joinCode.trim() || !joinName.trim()) {
      setError("Enter both quiz code and your name");
      return;
    }
    try {
      const res = await fetch(`${API}/api/quiz/${joinCode.trim().toUpperCase()}`);
      if (!res.ok) { setError("Quiz not found"); return; }
      onJoinGame(joinCode.trim().toUpperCase(), joinName.trim());
    } catch {
      setError("Cannot reach server. It may still be waking up.");
    }
  };

  return (
    <div className="landing">
      <div className="landing-bg">
        <div className="grid-lines" />
        <div className="glow glow-1" />
        <div className="glow glow-2" />
      </div>

      <header className="landing-header">
        <div className="logo">
          <span className="logo-icon">⚡</span>
          <span className="logo-text">QUIZARRE</span>
        </div>
        <p className="tagline">THINK FAST ACT FASTER!!</p>

        {serverStatus === "waking" && (
          <div style={{
            maxWidth: "460px",
            margin: "12px auto 0 auto",
            padding: "8px 16px",
            background: "rgba(245, 158, 11, 0.15)",
            border: "1px solid rgba(245, 158, 11, 0.4)",
            borderRadius: "8px",
            fontSize: "0.85rem",
            color: "#fcd34d",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: "8px"
          }}>
            <span style={{ fontSize: "1.1rem" }}>⏳</span>
            <span>Waking up free cloud backend... Ready in ~30s</span>
          </div>
        )}

        {serverStatus === "online" && (
          <div style={{
            maxWidth: "240px",
            margin: "10px auto 0 auto",
            padding: "4px 12px",
            background: "rgba(16, 185, 129, 0.12)",
            border: "1px solid rgba(16, 185, 129, 0.3)",
            borderRadius: "20px",
            fontSize: "0.76rem",
            color: "#6ee7b7",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: "6px"
          }}>
            <span style={{ width: "8px", height: "8px", borderRadius: "50%", background: "#10b981", display: "inline-block" }}></span>
            <span>Backend Online & Ready</span>
          </div>
        )}
      </header>

      <main className="landing-main">
        <div className="card host-card">
          <div className="card-badge">HOST</div>
          <h2>Run a Quiz</h2>
          <p>Upload CSV, manage questions, control the game flow</p>
          <button className="btn btn-primary" onClick={onHostGame}>
            Create Game <span>→</span>
          </button>
        </div>

        <div className="divider"><span>or</span></div>

        <div className="card join-card">
          <div className="card-badge player-badge">PLAYER</div>
          <h2>Join a Game</h2>
          <p>Enter the quiz code given by your host</p>
          <input
            className="input"
            placeholder="QUIZ CODE"
            value={joinCode}
            onChange={e => { setJoinCode(e.target.value.toUpperCase()); setError(""); }}
            maxLength={8}
          />
          <input
            className="input"
            placeholder="Your name"
            value={joinName}
            onChange={e => { setJoinName(e.target.value); setError(""); }}
            onKeyDown={e => e.key === "Enter" && handleJoin()}
          />
          {error && <p className="error-msg">{error}</p>}
          <button className="btn btn-secondary" onClick={handleJoin}>
            Join Game <span>→</span>
          </button>
        </div>
      </main>


    </div>
  );
}

function HostView({ playerId, onBack }) {
  const [step, setStep] = useState("upload");
  const [questions, setQuestions] = useState([]);
  const [uploadError, setUploadError] = useState("");
  const [quizTitle, setQuizTitle] = useState("My QUIZARRE");
  const [hostName, setHostName] = useState("Host");
  const [mode, setMode] = useState("buzzer"); // buzzer | classic
  const [quizId, setQuizId] = useState(null);
  const [gameState, setGameState] = useState(null);
  const wsRef = useRef(null);
  const fileRef = useRef(null);

  const connectWS = useCallback((qId) => {
    const ws = new WebSocket(`${WS_BASE}/ws/${qId}/${playerId}`);
    ws.onopen = () => {
      ws.send(JSON.stringify({ type: "join", name: hostName, role: "host" }));
    };
    ws.onmessage = (e) => {
      const msg = JSON.parse(e.data);
      if (msg.type === "state") setGameState(msg);
      if (msg.type === "wrong_answer") {
        setEvents(prev => [{ id: Date.now() + Math.random(), icon: "❌", text: `${msg.name} guessed "${msg.guess}" (Wrong!)` }, ...prev].slice(0, 50));
        setRecentWrong(`${msg.name} guessed: ${msg.guess || '?'}`);
        setTimeout(() => setRecentWrong(null), 3000);
      }
      if (msg.type === "correct_answer") {
        setEvents(prev => [{ id: Date.now() + Math.random(), icon: "✅", text: `${msg.name} chose "${msg.answer}" (Correct!)` }, ...prev].slice(0, 50));
      }
      if (msg.type === "your_turn") {
        setEvents(prev => [{ id: Date.now() + Math.random(), icon: "👉", text: `Turn passed to ${msg.name}` }, ...prev].slice(0, 50));
      }
      if (msg.type === "buzz_event") {
        setEvents(prev => [{ id: Date.now() + Math.random(), icon: "🔔", text: `${msg.name} hit the buzzer!` }, ...prev].slice(0, 50));
      }
      if (msg.type === "new_question") {
        setEvents([{ id: Date.now(), icon: "❓", text: `Question ${(msg.index || 0) + 1} started` }]);
      }
      if (msg.type === "player_joined") {
        setEvents(prev => [{ id: Date.now() + Math.random(), icon: "👋", text: `${msg.name} joined the room` }, ...prev].slice(0, 50));
      }
      if (msg.type === "player_left") {
        setEvents(prev => [{ id: Date.now() + Math.random(), icon: "🚪", text: `${msg.name} left the room` }, ...prev].slice(0, 50));
      }
      if (msg.type === "buzzer_update") {
        setGameState(prev => prev ? { ...prev, buzzer_queue: msg.queue, buzzer_names: msg.names } : prev);
      }
    };
    ws.onclose = () => setTimeout(() => connectWS(qId), 2000);
    wsRef.current = ws;
  }, [playerId, hostName]);

  const [elapsedSecs, setElapsedSecs] = useState(0);
  useEffect(() => {
    if (gameState?.status === "question") {
      setElapsedSecs(0);
      const interval = setInterval(() => {
        setElapsedSecs((prev) => prev + 0.25);
      }, 250);
      return () => clearInterval(interval);
    } else {
      setElapsedSecs(10);
    }
  }, [gameState?.current_index, gameState?.status]);

  useEffect(() => {
    if (gameState?.mode === "classic" && gameState?.status === "question" && elapsedSecs >= 30) {
      if (wsRef.current?.readyState === 1) {
        wsRef.current.send(JSON.stringify({ type: "skip_question" }));
      }
    }
  }, [elapsedSecs, gameState?.mode, gameState?.status]);

  useEffect(() => {
    if (gameState?.mode === "classic" && gameState?.status === "reviewing") {
      const timeout = setTimeout(() => {
        if (wsRef.current?.readyState === 1) {
          wsRef.current.send(JSON.stringify({ type: "next_question" }));
        }
      }, 5000); // 5s reveal time
      return () => clearTimeout(timeout);
    }
  }, [gameState?.status, gameState?.mode]);

  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    setUploadError("");
    const form = new FormData();
    form.append("file", file);
    try {
      const res = await fetch(`${API}/api/upload-csv`, { method: "POST", body: form });
      const data = await res.json();
      if (!res.ok) {
        const errs = data.detail?.errors || [data.detail];
        setUploadError(errs.join("\n"));
        return;
      }
      setQuestions(data.questions);
      setStep("preview");
    } catch {
      setUploadError("Upload failed – is the server running?");
    }
  };

  const handleCreateQuiz = async () => {
    try {
      const res = await fetch(`${API}/api/quiz/create`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ questions, title: quizTitle, host_name: hostName, mode }),
      });
      const data = await res.json();
      setQuizId(data.quiz_id);
      setStep("lobby");
      connectWS(data.quiz_id);
    } catch {
      setUploadError("Failed to create quiz");
    }
  };

  const send = (msg) => wsRef.current?.readyState === 1 && wsRef.current.send(JSON.stringify(msg));

  const startQuiz = () => {
    setStep("game");
    send({ type: "next_question" });
  };
  const nextQuestion = () => send({ type: "next_question" });
  const skipQuestion = () => send({ type: "skip_question" });

  const players = gameState?.players || {};
  const scores = gameState?.scores || {};
  const status = gameState?.status;
  const buzzerQueue = gameState?.buzzer_queue || [];
  const currentQ = gameState?.question;
  const answeringPlayer = gameState?.answering_player;
  const [recentWrong, setRecentWrong] = useState(null);
  const [events, setEvents] = useState([]);

  const sortedPlayers = Object.entries(scores)
    .filter(([pid]) => players[pid]?.role !== "host")
    .sort(([, a], [, b]) => b - a)
    .map(([pid, score]) => ({ pid, name: players[pid]?.name || pid, score, malpractice: players[pid]?.malpractice || 0 }));

  return (
    <div className="host-view">
      <div className="host-sidebar">
        <div className="sidebar-logo">
          <span>⚡</span> QUIZARRE
          <span className="host-badge">{gameState?.mode === 'classic' ? 'CLASSIC' : 'HOST'}</span>
        </div>

        {quizId && (
          <div className="quiz-code-box">
            <p className="code-label">ROOM CODE</p>
            <p className="code-value">{quizId}</p>
            <p className="code-hint">Share with players</p>
          </div>
        )}

        {step === "lobby" || step === "game" ? (
          <div className="player-list">
            <p className="section-label">PLAYERS ({Object.keys(players).filter(p => players[p]?.role === "player").length})</p>
            {Object.entries(players)
              .filter(([, p]) => p.role === "player")
              .map(([pid, p]) => (
                <div key={pid} className="player-row">
                  <span className="player-dot" />
                  <span>{p.name}</span>
                  {p.malpractice > 0 && (
                    <span className="malpractice-badge" title="Switched tabs!">⚠️ {p.malpractice}</span>
                  )}
                  <span className="player-score">{scores[pid] || 0} pts</span>
                </div>
              ))}
          </div>
        ) : null}

        <button className="btn-back" onClick={onBack}>← Back</button>
      </div>

      <div className="host-main">
        {step === "upload" && (
          <div className="upload-panel">
            <h1>Create Your Quiz</h1>
            <div className="form-group">
              <label>Quiz Title</label>
              <input className="input" value={quizTitle} onChange={e => setQuizTitle(e.target.value)} />
            </div>
            <div className="form-group">
              <label>Your Name</label>
              <input className="input" value={hostName} onChange={e => setHostName(e.target.value)} />
            </div>
            <div className="form-group" style={{ marginBottom: '20px' }}>
              <label>Game Mode</label>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px', marginTop: '4px' }}>
                <button 
                  type="button" 
                  className={`btn ${mode === 'buzzer' ? 'btn-primary' : 'btn-ghost'}`} 
                  onClick={() => setMode('buzzer')}
                >
                  🔔 Buzzer
                </button>
                <button 
                  type="button" 
                  className={`btn ${mode === 'classic' ? 'btn-primary' : 'btn-ghost'}`} 
                  onClick={() => setMode('classic')}
                  style={{ background: mode === 'classic' ? 'linear-gradient(135deg, #4f46e5, #7c3aed)' : '', color: mode === 'classic' ? 'white' : '' }}
                >
                  🎯 Classic
                </button>
              </div>
            </div>
            <div className="upload-zone" onClick={() => fileRef.current.click()}>
              <div className="upload-icon">📄</div>
              <p>Click to upload CSV file</p>
              <p className="upload-hint">Format: question, option1, option2, option3, option4, correct_option</p>
              <input ref={fileRef} type="file" accept=".csv" hidden onChange={handleFileUpload} />
            </div>
            {uploadError && (
              <div className="error-box">
                <strong>Validation Errors:</strong>
                <pre>{uploadError}</pre>
              </div>
            )}
          </div>
        )}
        {step === "preview" && (
          <div className="preview-panel">
            <h1>Preview Questions</h1>
            <p className="preview-count">{questions.length} questions loaded</p>
            <div className="preview-table-wrap">
              <table className="preview-table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Question</th>
                    <th>Options</th>
                    <th>Answer</th>
                  </tr>
                </thead>
                <tbody>
                  {questions.map((q, i) => (
                    <tr key={i}>
                      <td>{i + 1}</td>
                      <td>{q.question}</td>
                      <td className="options-cell">{q.options.join(", ")}</td>
                      <td className="correct-cell">{q.correct}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="preview-actions">
              <button className="btn btn-ghost" onClick={() => { setStep("upload"); setQuestions([]); }}>
                ← Re-upload
              </button>
              <button className="btn btn-primary" onClick={handleCreateQuiz}>
                Create Quiz Room →
              </button>
            </div>
          </div>
        )}
        {step === "lobby" && (gameState?.status === "lobby" || !gameState) && (
          <div className="lobby-panel">
            <h1>Waiting for Players</h1>
            <div className="big-code">
              <p>Room Code</p>
              <h2>{quizId}</h2>
            </div>
            <p className="lobby-hint">
              {Object.values(players).filter(p => p.role === "player").length} player(s) joined
            </p>
            <button className="btn btn-primary btn-large" onClick={startQuiz}>
              Start Quiz ⚡
            </button>
          </div>
        )}
        {(status === "question" || status === "reviewing" || status === "finished") && (
          <div className="game-panel">
            <div className="game-header" style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <span className="q-counter">
                Q{(gameState?.current_index ?? 0) + 1} / {gameState?.total_questions}
              </span>
              <span className={`status-badge status-${status}`}>{status.toUpperCase()}</span>
              {gameState?.mode === "classic" && status === "question" && (
                <span className="classic-counter" style={{ marginLeft: 'auto', background: '#4f46e5', color: 'white', padding: '5px 12px', borderRadius: '20px', fontSize: '0.85rem', fontWeight: '600', boxShadow: '0 2px 4px rgba(0,0,0,0.1)' }}>
                  👥 {gameState?.attempted?.length || 0} / {Object.values(players).filter(p => p.role === "player").length} Answered
                </span>
              )}
            </div>

            {currentQ && (
              <div className="question-box">
                <p className="question-text">{currentQ.text}</p>
                {((Date.now() / 1000) - (gameState?.question_start_time || 0) >= 5 || status === "reviewing") && (
                  <div className="options-grid">
                    {currentQ.options?.map((opt, i) => (
                      <div key={i} className={`option-chip ${status === "reviewing" && opt === currentQ.correct ? "option-correct" : ""}`}>
                        <span className="option-letter">{["A", "B", "C", "D"][i]}</span>
                        {opt}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {gameState?.mode === "classic" ? (
              <div className="classic-progress" style={{ margin: '20px 0' }}>
                <div className="progress-bar-wrap" style={{ height: '10px', background: 'rgba(255,255,255,0.1)', borderRadius: '5px', overflow: 'hidden' }}>
                  <div className="progress-bar-fill" style={{ height: '100%', background: elapsedSecs > 20 ? '#ef4444' : '#3b82f6', width: `${Math.max(0, 100 - (elapsedSecs / 30) * 100)}%`, transition: 'width 0.25s linear' }}></div>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.9rem', color: '#9ca3af', marginTop: '8px' }}>
                  <span>Time Left: {Math.max(0, Math.ceil(30 - elapsedSecs))}s</span>
                  <span>Answered: {gameState?.attempted?.length || 0} / {Object.values(players).filter(p => p.role === "player").length}</span>
                </div>
              </div>
            ) : (
              <div className="buzzer-section">
                <p className="section-label">BUZZER QUEUE</p>
                {buzzerQueue.length === 0 ? (
                  <p className="empty-queue">No buzzers yet</p>
                ) : (
                  <div className="queue-list">
                    {buzzerQueue.map((pid, i) => (
                      <div key={pid} className={`queue-item ${i === 0 ? "queue-first" : ""}`}>
                        <span className="queue-pos">{i + 1}</span>
                        <span>{players[pid]?.name || pid}</span>
                        {i === 0 && <span className="answering-tag">ANSWERING</span>}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            <div className="activity-feed">
              <p className="section-label">LIVE ACTIVITY LOG</p>
              <div className="feed-list">
                {events.length === 0 && <p className="empty-queue">No activity yet</p>}
                {events.map((ev) => (
                  <div key={ev.id} className="feed-item">
                    <span className="feed-icon">{ev.icon}</span>
                    <span className="feed-text">{ev.text}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="leaderboard-mini">
              <p className="section-label">SCORES</p>
              {sortedPlayers.slice(0, 5).map((p, i) => (
                <div key={p.pid} className="lb-row">
                  <span className="lb-rank">{["🥇", "🥈", "🥉", "4", "5"][i]}</span>
                  <span className="lb-name">{p.name}</span>
                  <span className="lb-score">{p.score}</span>
                </div>
              ))}
            </div>

            {status === "reviewing" && gameState?.mode === "classic" && (
              <div className="review-leaderboard-large" style={{ 
                position: 'fixed', 
                top: 0, left: 0, right: 0, bottom: 0, 
                background: 'rgba(0,0,0,0.85)', 
                display: 'flex', 
                flexDirection: 'column', 
                alignItems: 'center', 
                justifyContent: 'center', 
                zIndex: 9999, 
                padding: '20px' 
              }}>
                <div style={{ 
                  background: 'var(--surface)', 
                  padding: '30px', 
                  border: '1px solid var(--border)', 
                  borderRadius: '15px', 
                  width: '100%', 
                  maxWidth: '500px', 
                  boxShadow: '0 10px 30px rgba(0,0,0,0.25)', 
                  animation: 'slideIn 0.3s ease-out' 
                }}>
                  <h2 style={{ textAlign: 'center', marginBottom: '20px', fontFamily: 'var(--font-head)', letterSpacing: '2px', color: 'var(--accent)', fontSize: '1.8rem' }}>📊 LEADERBOARD</h2>
                  <div className="final-leaderboard" style={{ maxWidth: '100%', margin: '0' }}>
                    {sortedPlayers.slice(0, 20).map((p, i) => (
                      <div key={p.pid} className="final-row" style={{ padding: '12px 16px', background: 'var(--bg)', marginBottom: '8px' }}>
                        <span className="final-rank" style={{ fontSize: '1.2rem', fontWeight: '700', color: i < 3 ? 'var(--accent)' : 'var(--text3)' }}>{["🥇", "🥈", "🥉"][i] || i + 1}</span>
                        <span className="final-name" style={{ fontSize: '1rem', fontWeight: '600' }}>{p.name}</span>
                        <span className="final-score" style={{ fontSize: '1rem' }}>{p.score} pts</span>
                      </div>
                    ))}
                  </div>
                  <p style={{ textAlign: 'center', color: '#6b7280', fontSize: '0.85rem', marginTop: '15px' }}>Auto-advancing to next question in 5 seconds...</p>
                </div>
              </div>
            )}

            {status === "question" && (
              <div className="host-controls">
                <button className="btn btn-ghost" onClick={skipQuestion}>Skip / Reveal Answer</button>
              </div>
            )}
            {status === "reviewing" && (
              <div className="host-controls">
                <button className="btn btn-primary" onClick={nextQuestion}>
                  {(gameState?.current_index ?? 0) + 1 >= (gameState?.total_questions ?? 0)
                    ? "Finish Quiz ✓"
                    : "Next Question →"}
                </button>
              </div>
            )}
            {status === "finished" && (
              <div className="finished-box">
                <h2>🏆 Quiz Complete!</h2>
                <div className="final-leaderboard">
                  {sortedPlayers.map((p, i) => (
                    <div key={p.pid} className="final-row">
                      <span className="final-rank">{i + 1}</span>
                      <span className="final-name">{p.name}</span>
                      <span className="final-score">{p.score} pts</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
        {status === "lobby" && step !== "lobby" && (
          <div className="lobby-panel">
            <h1>Quiz Ready</h1>
            <p>Click Start Quiz when ready!</p>
            <button className="btn btn-primary btn-large" onClick={startQuiz}>Start Quiz ⚡</button>
          </div>
        )}
      </div>
    </div>
  );
}

// --- PlayerView ---
function PlayerView({ quizId, playerId, playerName, onBack }) {
  const [gameState, setGameState] = useState(null);
  const [lastEvent, setLastEvent] = useState(null);
  const [selectedAnswer, setSelectedAnswer] = useState(null);
  const [buzzed, setBuzzed] = useState(false);
  const [warnings, setWarnings] = useState(0);
  const [elapsedSecs, setElapsedSecs] = useState(0);
  const wsRef = useRef(null);
  const buzzerRef = useRef(null);

  // Audio synthesis for Buzzer
  const playBuzzSound = () => {
    try {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (!AudioCtx) return;
      const ctx = new AudioCtx();
      ctx.resume().then(() => {
        const osc1 = ctx.createOscillator();
        const osc2 = ctx.createOscillator();
        const gain = ctx.createGain();
        osc1.type = "sine";
        osc2.type = "sine";
        osc1.frequency.setValueAtTime(880, ctx.currentTime);
        osc2.frequency.setValueAtTime(1108.73, ctx.currentTime);
        gain.gain.setValueAtTime(0, ctx.currentTime);
        gain.gain.linearRampToValueAtTime(0.5, ctx.currentTime + 0.05);
        gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 1.0);
        osc1.connect(gain);
        osc2.connect(gain);
        gain.connect(ctx.destination);
        osc1.start(); osc2.start();
        osc1.stop(ctx.currentTime + 1.0); osc2.stop(ctx.currentTime + 1.0);
      }).catch(e => console.warn(e));
    } catch (e) { console.warn("Audio failed", e); }
  };

  const connect = useCallback(() => {
    const ws = new WebSocket(`${WS_BASE}/ws/${quizId}/${playerId}`);
    ws.onopen = () => {
      ws.send(JSON.stringify({ type: "join", name: playerName, role: "player" }));
    };
    ws.onmessage = (e) => {
      const msg = JSON.parse(e.data);
      handleMessage(msg);
    };
    ws.onclose = () => setTimeout(connect, 2000);
    wsRef.current = ws;
  }, [quizId, playerId, playerName]);

  useEffect(() => { connect(); return () => wsRef.current?.close(); }, [connect]);

  // Anti-cheat / Malpractice Listener
  useEffect(() => {
    const handleVis = () => {
      if (document.hidden) {
        setWarnings(w => w + 1);
        send({ type: "malpractice" });
      }
    };
    const handleBlur = () => {
      setWarnings(w => w + 1);
      send({ type: "malpractice" });
    };
    document.addEventListener("visibilitychange", handleVis);
    window.addEventListener("blur", handleBlur);
    return () => {
      document.removeEventListener("visibilitychange", handleVis);
      window.removeEventListener("blur", handleBlur);
    };
  }, []);

  useEffect(() => {
    if (gameState?.status === "question") {
      setElapsedSecs(0);
      const interval = setInterval(() => {
        setElapsedSecs((prev) => prev + 0.25);
      }, 250);
      return () => clearInterval(interval);
    } else {
      setElapsedSecs(10); // Safe override when not active
    }
  }, [gameState?.status, gameState?.current_index]);

  const handleMessage = (msg) => {
    if (msg.type === "state") {
      setGameState(msg);
    }
    if (msg.type === "new_question") {
      setBuzzed(false);
      setSelectedAnswer(null);
      setLastEvent(null);
      setGameState(prev => prev ? { ...prev, correct_answer: null, is_correct: null } : prev);
    }
    if (msg.type === "answer_feedback") {
      setGameState(prev => prev ? { ...prev, correct_answer: msg.correct, is_correct: msg.is_correct } : prev);
    }
    if (msg.type === "your_turn" || msg.type === "correct_answer" || msg.type === "reveal_answer") {
      setLastEvent(msg);
    }
    if (msg.type === "wrong_answer") {
      setLastEvent(msg);
      if (msg.player_id === playerId) {
        setSelectedAnswer(null);
      }
    }
    if (msg.type === "buzzer_update") {
      setGameState(prev => prev ? { ...prev, buzzer_queue: msg.queue, buzzer_names: msg.names } : prev);
    }
  };

  const send = (msg) => wsRef.current?.readyState === 1 && wsRef.current.send(JSON.stringify(msg));

  const handleBuzz = () => {
    if (buzzed) return;
    if (gameState?.status !== "question") return;
    if (isMyTurn) return;
    setBuzzed(true);
    playBuzzSound();
    send({ type: "buzz" });
    buzzerRef.current?.classList.add("buzz-animate");
    setTimeout(() => buzzerRef.current?.classList.remove("buzz-animate"), 600);
  };

  const handleAnswer = (opt) => {
    const isClassic = gameState?.mode === "classic";
    if (!isClassic && !isMyTurn) return;
    setSelectedAnswer(opt);
    send({ type: "answer", answer: opt });
  };

  const status = gameState?.status;
  const currentQ = gameState?.question;
  const buzzerQueue = gameState?.buzzer_queue || [];
  const players = gameState?.players || {};
  const scores = gameState?.scores || {};
  const isMyTurn = gameState?.answering_player === playerId;
  const myRank = buzzerQueue.indexOf(playerId);
  const isInQueue = myRank >= 0;

  const sortedScores = Object.entries(scores)
    .filter(([pid]) => players[pid]?.role !== "host")
    .sort(([, a], [, b]) => b - a)
    .map(([pid, score]) => ({ pid, name: players[pid]?.name || pid, score }));

  const lastCorrect = lastEvent?.type === "correct_answer";
  const lastWrong = lastEvent?.type === "wrong_answer" && lastEvent?.player_id === playerId;
  const revealAnswer = lastEvent?.type === "reveal_answer";

  const isClassic = gameState?.mode === "classic";
  const showOptions = isClassic 
    ? (status === "question" || status === "reviewing")
    : (elapsedSecs >= 5 || status === "reviewing" || buzzerQueue.length > 0);
  const showBuzzer = isClassic 
    ? false 
    : (elapsedSecs >= 8 || status === "reviewing" || buzzerQueue.length > 0);

  return (
    <div className={`player-view ${isMyTurn ? "my-turn" : ""} ${lastCorrect ? "correct-flash" : ""}`}>
      <div className="player-header">
        <div className="player-info">
          <span className="p-name">{playerName}</span>
          <span className="p-score">{scores[playerId] || 0} pts</span>
          {warnings > 0 && <span className="p-warning" title="Stay on the quiz tab!">⚠️ Warnings: {warnings}</span>}
        </div>
        <div className="room-tag">Room: {quizId}</div>
        <button className="btn-back-small" onClick={onBack}>×</button>
      </div>

      <div className="player-body">
        {(!status || status === "lobby") && (
          <div className="waiting-screen">
            <div className="waiting-pulse">⚡</div>
            <h2>Waiting for host to start...</h2>
            <p>Room code: <strong>{quizId}</strong></p>
          </div>
        )}

        {(status === "question" || status === "reviewing") && currentQ && (
          <>
            <div className="q-progress">
              <span>Q{(gameState?.current_index ?? 0) + 1} of {gameState?.total_questions}</span>
            </div>

            <div className={`question-card ${isMyTurn ? "question-card-active" : ""}`}>
              <p className="q-text">{currentQ.text}</p>
            </div>

            {showOptions && (
              <div className="answer-grid">
                {currentQ.options?.map((opt, i) => {
                  let cls = "answer-btn";
                  const isQuestion = status === "question";
                  
                  if (status === "reviewing" && opt === currentQ.correct) {
                    cls += " ans-correct";
                  } else if (selectedAnswer === opt) {
                    if (!(isClassic && isQuestion)) {
                      if (lastCorrect) cls += " ans-correct";
                      else cls += " ans-wrong";
                    }
                  }
                  
                  return (
                    <button
                      key={i}
                      className={cls}
                      onClick={() => handleAnswer(opt)}
                      disabled={(isClassic ? selectedAnswer !== null : !isMyTurn) || selectedAnswer !== null}
                      style={{ outline: 'none', boxShadow: 'none' }}
                    >
                      <span className="ans-letter">{["A", "B", "C", "D"][i]}</span>
                      {opt}
                    </button>
                  );
                })}
              </div>
            )}

            {isMyTurn && !selectedAnswer && (
              <div className="your-turn-banner">
                🎯 It's YOUR TURN! Pick an answer!
              </div>
            )}

            {isClassic && selectedAnswer && status === "question" && (
              <div className="your-turn-banner" style={{ background: '#047857' }}>
                ✅ Answer Submitted! Waiting for host...
              </div>
            )}
            
            {isClassic && !selectedAnswer && status === "question" && (
              <div className="your-turn-banner" style={{ background: '#0284c7' }}>
                ⚡ Select your answer fast! Time Is Running!
              </div>
            )}

            {lastWrong && (
              <div className="feedback-wrong">
                ✗ Wrong! Next player gets a chance.
              </div>
            )}

            {lastCorrect && (
              <div className="feedback-correct">
                {lastEvent.player_id === playerId
                  ? "🎉 Correct! +1 point!"
                  : `✅ ${lastEvent.name} got it right!`}
              </div>
            )}

            {revealAnswer && (
              <div className="feedback-reveal">
                📖 Answer: <strong>{lastEvent.correct}</strong>
              </div>
            )}

            {status === "question" && !isClassic && !isMyTurn && !isInQueue && (
              <div className="buzzer-area">
                <button
                  ref={buzzerRef}
                  className={`buzzer-btn ${buzzed || !showBuzzer ? "buzzed" : ""}`}
                  onClick={handleBuzz}
                  disabled={buzzed || !showBuzzer}
                >
                  <span className="buzzer-inner">
                    {buzzed ? "⏳ Queued!" : (!showBuzzer ? `Wait ${Math.ceil(8 - elapsedSecs)}s...` : "🔔 BUZZ!")}
                  </span>
                </button>
                {showBuzzer && <p className="buzzer-hint">Hit the buzzer to answer!</p>}
              </div>
            )}

            {status === "question" && isInQueue && !isMyTurn && (
              <div className="in-queue-badge">
                #{myRank + 1} in buzzer queue...
              </div>
            )}

            <div className="queue-display">
              <p className="section-label">BUZZER QUEUE</p>
              <div className="queue-track">
                {buzzerQueue.length === 0
                  ? <span className="quiet-queue">Waiting for buzzers...</span>
                  : buzzerQueue.map((pid, i) => (
                    <div key={pid} className={`queue-chip ${i === 0 ? "chip-first" : ""} ${pid === playerId ? "chip-me" : ""}`}>
                      {i === 0 && "🎤 "}{players[pid]?.name || pid}
                    </div>
                  ))
                }
              </div>
            </div>
          </>
        )}

        {status === "finished" && (
          <div className="finished-player">
            <h2>🏆 Quiz Over!</h2>
            <p>You scored <strong>{scores[playerId] || 0}</strong> points</p>
            <div className="final-lb">
              {sortedScores.slice(0, 10).map((p, i) => (
                <div key={p.pid} className={`final-row ${p.pid === playerId ? "final-row-me" : ""}`}>
                  <span>{["🥇", "🥈", "🥉", "4", "5", "6", "7", "8", "9", "10"][i] || i + 1}</span>
                  <span>{p.name}</span>
                  <span>{p.score} pts</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="player-sidebar">
        <p className="section-label">LEADERBOARD</p>
        {sortedScores.map((p, i) => (
          <div key={p.pid} className={`mini-lb-row ${p.pid === playerId ? "mini-lb-me" : ""}`}>
            <span className="mini-rank">{i + 1}</span>
            <span className="mini-name">{p.name}</span>
            <span className="mini-score">{p.score}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// --- App Root ---
function App() {
  const [view, setView] = useState("landing");
  const [quizId, setQuizId] = useState(null);
  const [playerId] = useState(() => {
    let id = localStorage.getItem("buzz_playerId");
    if (!id) {
      id = Math.random().toString(36).slice(2, 10);
      localStorage.setItem("buzz_playerId", id);
    }
    return id;
  });
  const [playerName, setPlayerName] = useState("");

  let currentView;
  if (view === "host") {
    currentView = <HostView playerId={playerId} onBack={() => setView("landing")} />;
  } else if (view === "player") {
    currentView = (
      <PlayerView
        quizId={quizId}
        playerId={playerId}
        playerName={playerName}
        onBack={() => setView("landing")}
      />
    );
  } else {
    currentView = (
      <LandingPage
        onHostGame={() => setView("host")}
        onJoinGame={(id, name) => {
          setQuizId(id);
          setPlayerName(name);
          setView("player");
        }}
      />
    );
  }

  return (
    <div className="min-h-screen flex flex-col">

      {/* Main Content */}
      <div className="flex-grow">
        {currentView}
      </div>

      {/* Footer */}
      <div className="creator-credit text-center py-3">
        <div className="creator-name">-Created by B M Tushyath</div>

        {view === "landing" && (
          <a
            href="https://www.linkedin.com/in/b-m-tushyath-793758282"
            target="_blank"
            rel="noreferrer"
            className="creator-link"
          >
            <svg className="linkedin-icon" viewBox="0 0 24 24" fill="currentColor">
              <path d="M19 0h-14c-2.761 0-5 2.239-5 5v14c0 2.761 2.239 5 5 5h14c2.762 0 5-2.239 5-5v-14c0-2.761-2.238-5-5-5zm-11 19h-3v-11h3v11zm-1.5-12.268c-.966 0-1.75-.79-1.75-1.764s.784-1.764 1.75-1.764 1.75.79 1.75 1.764-.783 1.764-1.75 1.764zm13.5 12.268h-3v-5.604c0-3.368-4-3.113-4 0v5.604h-3v-11h3v1.765c1.396-2.586 7-2.777 7 2.476v6.759z" />
            </svg>
            www.linkedin.com/in/b-m-tushyath-793758282
          </a>
        )}
      </div>

    </div>
  );
}

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
