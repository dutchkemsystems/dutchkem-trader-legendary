"use client";

import { useEffect, useState, useRef } from "react";
import Link from "next/link";

const FEATURES = [
  {
    icon: (
      <svg className="w-7 h-7" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0112 15a9.065 9.065 0 00-6.23.693L5 14.5m14.8.8l1.402 1.402c1.232 1.232.65 3.318-1.067 3.611A48.309 48.309 0 0112 21c-2.773 0-5.491-.235-8.135-.687-1.718-.293-2.3-2.379-1.067-3.61L5 14.5" />
      </svg>
    ),
    title: "12 AI Analysts",
    desc: "Parallel neural network analysis across fundamental, technical, and sentiment domains.",
    color: "from-cyan-400 to-blue-500",
  },
  {
    icon: (
      <svg className="w-7 h-7" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3.75 3v11.25A2.25 2.25 0 006 16.5h2.25M3.75 3h-1.5m1.5 0h16.5m0 0h1.5m-1.5 0v11.25A2.25 2.25 0 0118 16.5h-2.25m-7.5 0h7.5m-7.5 0l-1 3m8.5-3l1 3m0 0l.5 1.5m-.5-1.5h-9.5m0 0l-.5 1.5m.75-9l3-3 2.148 2.148A12.061 12.061 0 0116.5 7.605" />
      </svg>
    ),
    title: "7 Timeframes",
    desc: "D1 → M5 multi-timeframe confluence with weighted scoring for precision entries.",
    color: "from-blue-400 to-indigo-500",
  },
  {
    icon: (
      <svg className="w-7 h-7" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M10.5 6a7.5 7.5 0 107.5 7.5h-7.5V6z" />
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M13.5 10.5H21A7.5 7.5 0 0013.5 3v7.5z" />
      </svg>
    ),
    title: "Risk Engine",
    desc: "Dynamic Kelly criterion sizing with circuit breakers and correlation filters.",
    color: "from-indigo-400 to-purple-500",
  },
  {
    icon: (
      <svg className="w-7 h-7" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z" />
      </svg>
    ),
    title: "Reinforcement Learning",
    desc: "Self-evolving strategies that learn from every trade outcome in real time.",
    color: "from-purple-400 to-pink-500",
  },
];

const STATS = [
  { value: "27", label: "Instruments", suffix: "" },
  { value: "7", label: "Timeframes", suffix: "" },
  { value: "12", label: "AI Analysts", suffix: "" },
  { value: "99.9", label: "Uptime", suffix: "%" },
];

const TESTIMONIALS = [
  {
    quote: "The multi-timeframe confluence catches trades I would have missed entirely. It's like having 7 screens working for me.",
    author: "Marcus W.",
    role: "Forex Specialist",
  },
  {
    quote: "Risk management is institutional-grade. Drawdowns are minimal and position sizing adapts to volatility automatically.",
    author: "Sarah K.",
    role: "Quant Developer",
  },
  {
    quote: "Best autonomous trading system I've used. The AI debate engine alone is worth the price of admission.",
    author: "James R.",
    role: "Crypto & Indices",
  },
];

const TICKER_ITEMS = [
  "EURUSD +0.12%", "GBPUSD -0.08%", "USDJPY +0.34%", "XAUUSD +1.21%",
  "BTCUSD +2.45%", "ETHUSD +1.87%", "US30 +0.56%", "NVDA +3.21%",
  "AAPL +0.89%", "AMD +4.12%",
];

function AnimatedCounter({ target, suffix }: { target: string; suffix: string }) {
  const [count, setCount] = useState("0");
  const ref = useRef<HTMLDivElement>(null);
  const animated = useRef(false);

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && !animated.current) {
          animated.current = true;
          const num = parseFloat(target);
          const duration = 2000;
          const startTime = Date.now();
          const animate = () => {
            const elapsed = Date.now() - startTime;
            const progress = Math.min(elapsed / duration, 1);
            const eased = 1 - Math.pow(1 - progress, 3);
            const current = num * eased;
            setCount(num % 1 !== 0 ? current.toFixed(1) : Math.round(current).toString());
            if (progress < 1) requestAnimationFrame(animate);
          };
          requestAnimationFrame(animate);
        }
      },
      { threshold: 0.5 }
    );
    if (ref.current) observer.observe(ref.current);
    return () => observer.disconnect();
  }, [target]);

  return (
    <div ref={ref} className="text-5xl md:text-6xl font-black bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-transparent">
      {count}{suffix}
    </div>
  );
}

export default function HomePage() {
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 });
  const [loaded, setLoaded] = useState(false);
  const [scrollY, setScrollY] = useState(0);

  useEffect(() => {
    setLoaded(true);
    const handleMouseMove = (e: MouseEvent) => {
      setMousePos({ x: e.clientX, y: e.clientY });
    };
    const handleScroll = () => setScrollY(window.scrollY);
    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("scroll", handleScroll, { passive: true });

    // Scroll reveal
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("visible");
          }
        });
      },
      { threshold: 0.1 }
    );
    document.querySelectorAll(".reveal, .stagger-children").forEach((el) => observer.observe(el));

    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("scroll", handleScroll);
      observer.disconnect();
    };
  }, []);

  return (
    <div className="min-h-screen bg-black text-white overflow-hidden">
      {/* ═══════════ Animated Background ═══════════ */}
      <div className="fixed inset-0 z-0">
        {/* Cursor-following gradient orb */}
        <div
          className="absolute w-[700px] h-[700px] rounded-full opacity-15 blur-[140px] transition-all duration-500 ease-out pointer-events-none"
          style={{
            background: "radial-gradient(circle, #06b6d4 0%, transparent 70%)",
            left: mousePos.x - 350,
            top: mousePos.y - 350,
          }}
        />
        {/* Static orbs */}
        <div className="absolute top-[15%] left-[20%] w-[500px] h-[500px] rounded-full opacity-[0.07] blur-[120px] bg-violet-600 animate-pulse-slow" />
        <div className="absolute bottom-[20%] right-[15%] w-[450px] h-[450px] rounded-full opacity-[0.07] blur-[120px] bg-cyan-500 animate-pulse-slow" style={{ animationDelay: "2s" }} />
        <div className="absolute top-[60%] left-[60%] w-[350px] h-[350px] rounded-full opacity-[0.05] blur-[100px] bg-blue-600 animate-pulse-slow" style={{ animationDelay: "4s" }} />

        {/* Perspective grid */}
        <div
          className="absolute inset-0 opacity-[0.025]"
          style={{
            backgroundImage: `linear-gradient(rgba(6,182,212,0.3) 1px, transparent 1px), linear-gradient(90deg, rgba(6,182,212,0.3) 1px, transparent 1px)`,
            backgroundSize: "80px 80px",
          }}
        />

        {/* Floating particles */}
        {[...Array(30)].map((_, i) => (
          <div
            key={i}
            className="absolute rounded-full animate-float"
            style={{
              width: `${1 + Math.random() * 3}px`,
              height: `${1 + Math.random() * 3}px`,
              left: `${Math.random() * 100}%`,
              top: `${Math.random() * 100}%`,
              background: i % 3 === 0 ? "#06b6d4" : i % 3 === 1 ? "#3b82f6" : "#8b5cf6",
              opacity: 0.2 + Math.random() * 0.3,
              animationDelay: `${Math.random() * 8}s`,
              animationDuration: `${4 + Math.random() * 6}s`,
            }}
          />
        ))}
      </div>

      {/* ═══════════ Content ═══════════ */}
      <div className="relative z-10">
        {/* ─── Ticker Tape ─── */}
        <div className="fixed top-0 left-0 right-0 z-50 bg-black/70 backdrop-blur-xl border-b border-white/5 overflow-hidden h-8 flex items-center">
          <div className="flex animate-[scroll_40s_linear_infinite] whitespace-nowrap">
            {[...TICKER_ITEMS, ...TICKER_ITEMS, ...TICKER_ITEMS].map((item, i) => {
              const isUp = item.includes("+");
              return (
                <span key={i} className="inline-flex items-center gap-2 px-6 text-xs font-mono">
                  <span className="text-gray-500">{item.split(" ")[0]}</span>
                  <span className={isUp ? "text-emerald-400" : "text-red-400"}>
                    {item.split(" ")[1]}
                  </span>
                  <span className="text-gray-700">|</span>
                </span>
              );
            })}
          </div>
        </div>

        {/* ─── Navigation ─── */}
        <nav className="fixed top-8 left-0 right-0 z-50 backdrop-blur-2xl bg-black/40 border-b border-white/5">
          <div className="max-w-7xl mx-auto px-6 py-3.5 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-cyan-400 to-blue-600 flex items-center justify-center font-black text-black text-sm tracking-tight shadow-lg shadow-cyan-500/20">
                DK
              </div>
              <div>
                <span className="text-lg font-bold tracking-tight">DutchKEM</span>
                <span className="text-[10px] text-cyan-400 ml-2 font-medium tracking-widest uppercase">Trader</span>
              </div>
            </div>
            <div className="hidden md:flex items-center gap-8 text-sm text-gray-400">
              <a href="#features" className="hover:text-white transition-colors duration-300">Features</a>
              <a href="#performance" className="hover:text-white transition-colors duration-300">Performance</a>
              <a href="#reviews" className="hover:text-white transition-colors duration-300">Reviews</a>
            </div>
            <div className="flex items-center gap-3">
              <Link href="/login" className="px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors duration-300">
                Sign In
              </Link>
              <Link
                href="/dashboard"
                className="group px-6 py-2.5 bg-gradient-to-r from-cyan-500 to-blue-600 rounded-xl font-semibold text-sm hover:shadow-lg hover:shadow-cyan-500/25 transition-all duration-300 hover:scale-[1.03] animate-glow"
              >
                Launch Dashboard
              </Link>
            </div>
          </div>
        </nav>

        {/* ═══════════ HERO ═══════════ */}
        <section className="min-h-screen flex items-center justify-center px-6 pt-28">
          <div className="max-w-5xl mx-auto text-center">
            {/* Status badge */}
            <div
              className={`inline-flex items-center gap-2.5 px-5 py-2 rounded-full bg-white/[0.03] border border-white/[0.06] text-sm text-gray-400 mb-10 transition-all duration-1000 ${
                loaded ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"
              }`}
            >
              <span className="relative flex h-2.5 w-2.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-400" />
              </span>
              Live Trading Active &mdash; 27 Instruments
            </div>

            {/* Main headline */}
            <h1
              className={`text-7xl md:text-[9rem] font-black leading-[0.9] tracking-tighter mb-8 transition-all duration-1000 delay-200 ${
                loaded ? "opacity-100 translate-y-0" : "opacity-0 translate-y-10"
              }`}
            >
              <span className="block text-gradient-animated">DutchKEM</span>
              <span className="block text-white/90">Trader</span>
            </h1>

            {/* Subtitle */}
            <p
              className={`text-xl md:text-2xl text-gray-400 max-w-2xl mx-auto mb-14 leading-relaxed transition-all duration-1000 delay-400 ${
                loaded ? "opacity-100 translate-y-0" : "opacity-0 translate-y-10"
              }`}
            >
              12 AI analysts. 7 timeframes. Reinforcement learning.
              <br />
              <span className="text-cyan-400 font-semibold">Autonomous trading that evolves.</span>
            </p>

            {/* CTA buttons */}
            <div
              className={`flex flex-col sm:flex-row gap-4 justify-center transition-all duration-1000 delay-[600ms] ${
                loaded ? "opacity-100 translate-y-0" : "opacity-0 translate-y-10"
              }`}
            >
              <Link
                href="/dashboard"
                className="group relative px-10 py-5 bg-gradient-to-r from-cyan-500 to-blue-600 rounded-2xl font-bold text-lg overflow-hidden hover:shadow-2xl hover:shadow-cyan-500/30 transition-all duration-300 hover:scale-[1.04]"
              >
                <span className="relative z-10 flex items-center justify-center gap-2">
                  Start Trading
                  <svg className="w-5 h-5 group-hover:translate-x-1.5 transition-transform duration-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M13 7l5 5m0 0l-5 5m5-5H6" />
                  </svg>
                </span>
                <div className="absolute inset-0 bg-gradient-to-r from-cyan-400 to-blue-500 opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
              </Link>
              <a
                href="#features"
                className="px-10 py-5 bg-white/[0.04] border border-white/[0.08] rounded-2xl font-bold text-lg hover:bg-white/[0.08] transition-all duration-300 flex items-center justify-center"
              >
                Explore Features
              </a>
            </div>

            {/* Stats */}
            <div
              className={`mt-24 grid grid-cols-2 md:grid-cols-4 gap-10 max-w-4xl mx-auto transition-all duration-1000 delay-[800ms] ${
                loaded ? "opacity-100 translate-y-0" : "opacity-0 translate-y-10"
              }`}
            >
              {STATS.map((stat, i) => (
                <div key={i} className="text-center">
                  <AnimatedCounter target={stat.value} suffix={stat.suffix} />
                  <div className="text-sm text-gray-500 mt-2 font-medium tracking-wide uppercase">{stat.label}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Scroll indicator */}
          <div className="absolute bottom-10 left-1/2 -translate-x-1/2 flex flex-col items-center gap-2 animate-bounce">
            <span className="text-[10px] text-gray-600 uppercase tracking-widest">Scroll</span>
            <svg className="w-5 h-5 text-gray-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 14l-7 7m0 0l-7-7m7 7V3" />
            </svg>
          </div>
        </section>

        {/* ═══════════ FEATURES ═══════════ */}
        <section id="features" className="py-32 px-6 relative">
          <div className="max-w-6xl mx-auto">
            <div className="text-center mb-20 reveal">
              <span className="inline-block px-4 py-1.5 rounded-full bg-cyan-500/10 text-cyan-400 text-xs font-semibold tracking-widest uppercase mb-6">
                Core Engine
              </span>
              <h2 className="text-5xl md:text-7xl font-black tracking-tight mb-6">
                Built to{" "}
                <span className="text-gradient-animated">Dominate</span>
              </h2>
              <p className="text-xl text-gray-400 max-w-2xl mx-auto">
                Every component engineered for one purpose: consistent, risk-adjusted returns.
              </p>
            </div>

            <div className="grid md:grid-cols-2 gap-6 stagger-children">
              {FEATURES.map((f, i) => (
                <div
                  key={i}
                  className="group relative p-10 rounded-3xl glass border border-white/[0.06] hover:border-cyan-500/20 transition-all duration-500 hover:shadow-2xl hover:shadow-cyan-500/5 hover:-translate-y-1 overflow-hidden"
                >
                  {/* Glow on hover */}
                  <div className={`absolute -top-20 -right-20 w-40 h-40 bg-gradient-to-br ${f.color} rounded-full opacity-0 group-hover:opacity-10 blur-[80px] transition-opacity duration-700`} />
                  <div className={`w-14 h-14 rounded-2xl bg-gradient-to-br ${f.color} bg-opacity-20 flex items-center justify-center text-white/80 mb-6 group-hover:scale-110 transition-transform duration-500 shadow-lg`}>
                    {f.icon}
                  </div>
                  <h3 className="text-2xl font-bold mb-3 tracking-tight">{f.title}</h3>
                  <p className="text-gray-400 leading-relaxed">{f.desc}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ═══════════ PERFORMANCE SECTION ═══════════ */}
        <section id="performance" className="py-32 px-6 relative">
          <div className="absolute inset-0 bg-gradient-to-b from-cyan-500/[0.03] to-transparent" />
          <div className="max-w-6xl mx-auto relative">
            <div className="grid md:grid-cols-2 gap-20 items-center">
              {/* Left text */}
              <div className="reveal">
                <span className="inline-block px-4 py-1.5 rounded-full bg-cyan-500/10 text-cyan-400 text-xs font-semibold tracking-widest uppercase mb-6">
                  Results
                </span>
                <h2 className="text-5xl md:text-6xl font-black tracking-tight mb-6">
                  Trading that{" "}
                  <span className="text-gradient-animated">learns</span>
                </h2>
                <p className="text-lg text-gray-400 mb-10 leading-relaxed">
                  Our reinforcement learning engine analyzes every trade, adapts to changing markets,
                  and continuously improves its edge. The more it runs, the sharper it gets.
                </p>
                <div className="space-y-5">
                  {[
                    "Real-time analysis across 7 timeframes simultaneously",
                    "Dynamic Kelly criterion position sizing",
                    "Volatility-adaptive stop losses and take profits",
                    "Correlation-aware portfolio construction",
                    "News-avoidance and spread filtering built in",
                  ].map((item, i) => (
                    <div key={i} className="flex items-start gap-4 group/item">
                      <div className="w-6 h-6 rounded-lg bg-emerald-500/15 flex items-center justify-center flex-shrink-0 mt-0.5 group-hover/item:bg-emerald-500/25 transition-colors">
                        <svg className="w-3.5 h-3.5 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                        </svg>
                      </div>
                      <span className="text-gray-300 leading-snug">{item}</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Right card */}
              <div className="relative reveal">
                <div className="absolute inset-0 bg-gradient-to-r from-cyan-500 to-blue-600 rounded-3xl blur-[80px] opacity-10 animate-pulse-slow" />
                <div className="relative p-10 rounded-3xl glass border border-white/[0.08]">
                  {/* Header */}
                  <div className="flex items-center justify-between mb-8">
                    <div className="flex items-center gap-3">
                      <span className="relative flex h-3 w-3">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60" />
                        <span className="relative inline-flex rounded-full h-3 w-3 bg-emerald-400" />
                      </span>
                      <span className="text-sm text-gray-400 font-medium">Live Performance</span>
                    </div>
                    <span className="text-xs text-gray-600 font-mono">2026</span>
                  </div>

                  {/* Stats grid */}
                  <div className="grid grid-cols-2 gap-4 mb-8">
                    {[
                      { label: "Backtest P&L", value: "+$246.56", color: "text-emerald-400", bg: "bg-emerald-500/10" },
                      { label: "Win Rate", value: "73%", color: "text-cyan-400", bg: "bg-cyan-500/10" },
                      { label: "Total Trades", value: "1,422", color: "text-blue-400", bg: "bg-blue-500/10" },
                      { label: "Instruments", value: "27", color: "text-purple-400", bg: "bg-purple-500/10" },
                    ].map((s, i) => (
                      <div key={i} className={`p-5 rounded-2xl ${s.bg} border border-white/[0.04]`}>
                        <div className={`text-3xl font-black ${s.color}`}>{s.value}</div>
                        <div className="text-xs text-gray-500 mt-1.5 font-medium">{s.label}</div>
                      </div>
                    ))}
                  </div>

                  {/* Equity chart */}
                  <div className="h-40 rounded-2xl bg-gradient-to-r from-cyan-500/[0.06] to-blue-500/[0.06] border border-cyan-500/10 flex items-end justify-between px-4 pb-4 pt-6 relative overflow-hidden">
                    <span className="absolute top-3 left-4 text-[10px] text-gray-600 uppercase tracking-widest font-medium">Equity Curve</span>
                    <svg className="absolute inset-0 w-full h-full" viewBox="0 0 400 120" preserveAspectRatio="none">
                      <defs>
                        <linearGradient id="eqGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                          <stop offset="0%" stopColor="#06b6d4" />
                          <stop offset="100%" stopColor="#3b82f6" />
                        </linearGradient>
                        <linearGradient id="fillGrad" x1="0%" y1="0%" x2="0%" y2="100%">
                          <stop offset="0%" stopColor="#06b6d4" stopOpacity="0.15" />
                          <stop offset="100%" stopColor="#06b6d4" stopOpacity="0" />
                        </linearGradient>
                      </defs>
                      <path
                        d="M0,100 Q30,95 60,85 T120,70 T180,50 T240,35 T300,25 T360,15 L400,10 L400,120 L0,120 Z"
                        fill="url(#fillGrad)"
                      />
                      <path
                        d="M0,100 Q30,95 60,85 T120,70 T180,50 T240,35 T300,25 T360,15 L400,10"
                        fill="none"
                        stroke="url(#eqGrad)"
                        strokeWidth="2.5"
                        className="animate-draw"
                      />
                    </svg>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ═══════════ TESTIMONIALS ═══════════ */}
        <section id="reviews" className="py-32 px-6">
          <div className="max-w-6xl mx-auto">
            <div className="text-center mb-20 reveal">
              <span className="inline-block px-4 py-1.5 rounded-full bg-purple-500/10 text-purple-400 text-xs font-semibold tracking-widest uppercase mb-6">
                Testimonials
              </span>
              <h2 className="text-5xl md:text-7xl font-black tracking-tight">
                Trusted by{" "}
                <span className="text-gradient-animated">Traders</span>
              </h2>
            </div>

            <div className="grid md:grid-cols-3 gap-6 stagger-children">
              {TESTIMONIALS.map((t, i) => (
                <div
                  key={i}
                  className="group p-8 rounded-3xl glass border border-white/[0.06] hover:border-purple-500/20 transition-all duration-500 hover:-translate-y-1"
                >
                  <div className="flex gap-1 mb-5">
                    {[...Array(5)].map((_, j) => (
                      <svg key={j} className="w-5 h-5 text-amber-400" fill="currentColor" viewBox="0 0 20 20">
                        <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
                      </svg>
                    ))}
                  </div>
                  <p className="text-gray-300 text-lg leading-relaxed mb-8 italic">
                    &ldquo;{t.quote}&rdquo;
                  </p>
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full bg-gradient-to-br from-cyan-400 to-blue-600 flex items-center justify-center text-black font-bold text-xs">
                      {t.author.split(" ").map(n => n[0]).join("")}
                    </div>
                    <div>
                      <div className="font-bold text-sm">{t.author}</div>
                      <div className="text-xs text-gray-500">{t.role}</div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ═══════════ FINAL CTA ═══════════ */}
        <section className="py-32 px-6 relative">
          <div className="absolute inset-0 bg-gradient-to-b from-transparent via-cyan-500/[0.03] to-transparent" />
          <div className="max-w-4xl mx-auto text-center relative reveal">
            <h2 className="text-6xl md:text-8xl font-black tracking-tight mb-8">
              Ready to{" "}
              <span className="text-gradient-animated">Trade</span>?
            </h2>
            <p className="text-xl text-gray-400 mb-14 max-w-2xl mx-auto leading-relaxed">
              Start with a demo account. Go live when you&apos;re confident.
              <br />
              No credit card required.
            </p>
            <Link
              href="/dashboard"
              className="group inline-flex items-center gap-3 px-12 py-6 bg-gradient-to-r from-cyan-500 to-blue-600 rounded-2xl font-bold text-xl hover:shadow-2xl hover:shadow-cyan-500/30 transition-all duration-300 hover:scale-[1.04] animate-glow"
            >
              Launch Dashboard
              <svg className="w-6 h-6 group-hover:translate-x-1.5 transition-transform duration-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M13 7l5 5m0 0l-5 5m5-5H6" />
              </svg>
            </Link>
          </div>
        </section>

        {/* ═══════════ FOOTER ═══════════ */}
        <footer className="border-t border-white/5 py-14 px-6">
          <div className="max-w-6xl mx-auto flex flex-col md:flex-row items-center justify-between gap-6">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-cyan-400 to-blue-600 flex items-center justify-center font-black text-black text-xs">DK</div>
              <span className="font-bold text-sm">DutchKEM Trader</span>
            </div>
            <div className="text-sm text-gray-600">
              DutchKEM Trader &mdash; Powered by AI &mdash; 2026
            </div>
          </div>
        </footer>
      </div>

      {/* ═══════════ Global Animations ═══════════ */}
      <style jsx global>{`
        @keyframes scroll {
          from { transform: translateX(0); }
          to { transform: translateX(-33.33%); }
        }
      `}</style>
    </div>
  );
}
