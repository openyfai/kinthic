"use client";

import { AiNetworkIcon as Network, Loading01Icon as Loader2, Cancel01Icon as X, Tag01Icon as Tag, Layers01Icon as Layers, Chart01Icon as BarChart2, HashtagIcon as Hash } from 'hugeicons-react';
import { MutableRefObject, useEffect, useState, useRef, useCallback } from 'react';
import dynamic from 'next/dynamic';
import { apiUrl, getAuthHeaders } from '@/lib/api';

const ForceGraph2D = dynamic(() => import('react-force-graph-2d'), { ssr: false });

interface GraphNode {
  id: string;
  label: string;
  group: string;
  val: number;
  x?: number;
  y?: number;
}

interface GraphLink {
  source: string | GraphNode;
  target: string | GraphNode;
  label: string;
  strength: number;
}

type GraphMethods = {
  d3Force: (name: string) => { strength?: (value: number) => void; distance?: (value: number) => void } | undefined;
  d3ReheatSimulation: () => void;
  centerAt: (x?: number, y?: number, duration?: number) => void;
  zoom: (k: number, duration?: number) => void;
};

const GROUP_META: Record<string, { color: string; bg: string; text: string; badge: string }> = {
  fact:        { color: '#A5B4FC', bg: 'bg-secondary',   text: 'text-foreground',  badge: 'Fact' },
  belief:      { color: '#FCD34D', bg: 'bg-secondary',  text: 'text-foreground', badge: 'Belief' },
  observation: { color: '#F87171', bg: 'bg-secondary',    text: 'text-foreground',   badge: 'Observation' },
};

export default function GraphView() {
  const [nodes, setNodes]         = useState<GraphNode[]>([]);
  const [links, setLinks]         = useState<GraphLink[]>([]);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState<string | null>(null);
  const [selected, setSelected]   = useState<GraphNode | null>(null);
  const containerRef              = useRef<HTMLDivElement>(null);
  const fgRef                     = useRef<GraphMethods | undefined>(undefined);
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 });

  // ── Fetch graph data ───────────────────────────────────────────────────────
  useEffect(() => {
    fetch(apiUrl('/api/graph'), { headers: getAuthHeaders() })
      .then(res => {
        if (!res.ok) throw new Error("Failed to load graph");
        return res.json();
      })
      .then(data => {
        setNodes(data.nodes || []);
        setLinks(data.links || []);
        setLoading(false);
      })
      .catch(err => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  // ── Tune physics once loaded ───────────────────────────────────────────────
  useEffect(() => {
    const graph = fgRef.current as GraphMethods | undefined;
    if (graph && !loading && nodes.length > 0) {
      graph.d3Force('charge')?.strength?.(-800);
      graph.d3Force('link')?.distance?.(100);
      graph.d3ReheatSimulation();
    }
  }, [loading, nodes]);

  // ── Container resize ──────────────────────────────────────────────────────
  useEffect(() => {
    const update = () => {
      if (containerRef.current) {
        setDimensions({
          width:  containerRef.current.clientWidth,
          height: containerRef.current.clientHeight,
        });
      }
    };
    update();
    window.addEventListener('resize', update);
    return () => window.removeEventListener('resize', update);
  }, [loading]);

  // ── Helpers ────────────────────────────────────────────────────────────────
  const getNodeColor = useCallback((node: unknown) => {
    const graphNode = node as GraphNode;
    return GROUP_META[graphNode.group]?.color ?? '#A5B4FC';
  }, []);

  // ── Canvas renderer ───────────────────────────────────────────────────────
  const drawNode = useCallback((node: unknown, ctx: CanvasRenderingContext2D, globalScale: number) => {
    const graphNode = node as GraphNode;
    const isSelected = selected?.id === graphNode.id;
    const r = Math.max(4, graphNode.val || 5);
    const x = graphNode.x ?? 0;
    const y = graphNode.y ?? 0;

    // Selection ring
    if (isSelected) {
      ctx.beginPath();
      ctx.arc(x, y, r + 4, 0, 2 * Math.PI, false);
      ctx.fillStyle = 'rgba(99, 102, 241, 0.2)';
      ctx.fill();
      ctx.strokeStyle = '#6366F1';
      ctx.lineWidth = 1.5;
      ctx.stroke();
    }

    // Node circle
    ctx.beginPath();
    ctx.arc(x, y, r, 0, 2 * Math.PI, false);
    ctx.fillStyle = getNodeColor(graphNode);
    ctx.fill();
    ctx.strokeStyle = isSelected ? '#818CF8' : 'rgba(255, 255, 255, 0.25)';
    ctx.lineWidth = isSelected ? 2 : 0.8;
    ctx.stroke();

    // Label (only when zoomed in enough)
    if (globalScale > 0.8 || (graphNode.val && graphNode.val > 7)) {
      const fontSize = Math.max(3.5, 10 / globalScale);
      ctx.font = `${fontSize}px Inter, sans-serif`;
      const textWidth = ctx.measureText(graphNode.label).width;
      const pad = fontSize * 0.4;

      // Dark translucent pill background
      ctx.fillStyle = 'rgba(0, 0, 0, 0.65)';
      const rx = x - textWidth / 2 - pad / 2;
      const ry = y + r + 2;
      const rw = textWidth + pad;
      const rh = fontSize + pad;
      ctx.beginPath();
      ctx.roundRect(rx, ry, rw, rh, 3);
      ctx.fill();

      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      ctx.fillStyle = isSelected ? '#A5B4FC' : '#ECECEC';
      ctx.fillText(graphNode.label, x, y + r + 2 + pad * 0.4);
    }
  }, [getNodeColor, selected]);

  // ── Node click handler ────────────────────────────────────────────────────
  const handleNodeClick = useCallback((node: unknown) => {
    const graphNode = node as GraphNode;
    setSelected(prev => prev?.id === graphNode.id ? null : graphNode);
    // Zoom to node
    const graph = fgRef.current as GraphMethods | undefined;
    if (graph) {
      graph.centerAt(graphNode.x, graphNode.y, 600);
      graph.zoom(2.5, 600);
    }
  }, []);

  const handleClose = () => {
    setSelected(null);
    const graph = fgRef.current as GraphMethods | undefined;
    if (graph) graph.zoom(1, 500);
  };

  // ── Render ────────────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Loader2 size={24} className="animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex-1 flex items-center justify-center text-red-500 text-sm">
        {error}
      </div>
    );
  }

  const meta = selected ? (GROUP_META[selected.group] ?? GROUP_META['fact']) : null;

  return (
    <div className="flex-1 flex flex-col px-4 py-8 relative">
      {/* Header */}
      <div className="max-w-4xl mx-auto w-full">
        <div className="flex items-center gap-3 mb-4">
          <Network size={24} className="text-foreground" />
          <h1 className="text-2xl font-semibold tracking-tight">Knowledge Graph</h1>
          <span className="ml-auto text-xs text-muted-foreground font-medium">
            {nodes.length} nodes · {links.length} edges
          </span>
        </div>
      </div>

      {/* Graph + detail panel wrapper */}
      <div className="flex-1 w-full max-w-5xl mx-auto relative flex gap-3">
        {/* Canvas */}
        <div
          className="flex-1 relative rounded-2xl overflow-hidden border border-border shadow-sm bg-background"
          ref={containerRef}
        >
          {nodes.length === 0 ? (
            <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
              <Network size={32} className="mx-auto text-muted-foreground mb-3" />
              <p className="text-muted-foreground text-sm font-medium">Knowledge graph is empty.</p>
              <p className="text-muted-foreground text-xs mt-1">Chat with ARIA to build her knowledge graph.</p>
            </div>
          ) : (
            <ForceGraph2D
              ref={fgRef as unknown as MutableRefObject<undefined>}
              width={dimensions.width}
              height={dimensions.height}
              graphData={{ nodes, links }}
              nodeLabel={() => ""}
              nodeCanvasObject={drawNode}
              onNodeClick={handleNodeClick}
              linkColor={() => "rgba(255, 255, 255, 0.18)"}
              linkWidth={1.5}
              linkDirectionalArrowLength={4}
              linkDirectionalArrowRelPos={1}
              d3AlphaDecay={0.02}
              d3VelocityDecay={0.3}
            />
          )}
        </div>

        {/* Sliding Detail Panel */}
        {selected && meta && (
          <div
            className="w-72 rounded-2xl border border-border shadow-sm bg-background p-5 flex flex-col gap-4 animate-fade-in"
            style={{ animation: 'slideIn 0.2s ease-out' }}
          >
            {/* Panel header */}
            <div className="flex items-start justify-between">
              <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${meta.bg} ${meta.text}`}>
                {meta.badge}
              </span>
              <button
                onClick={handleClose}
                className="p-1 rounded-lg hover:bg-secondary text-muted-foreground hover:text-muted-foreground transition-colors"
              >
                <X size={14} />
              </button>
            </div>

            {/* Node label */}
            <p className="text-sm font-semibold text-foreground leading-snug">
              {selected.label}
            </p>

            <div className="h-px bg-secondary" />

            {/* Metadata rows */}
            <div className="flex flex-col gap-3">
              <MetaRow icon={<Hash size={13} />} label="Node ID" value={selected.id} mono />
              <MetaRow icon={<Layers size={13} />} label="Group" value={selected.group} />
              <MetaRow
                icon={<BarChart2 size={13} />}
                label="Confidence"
                value={`${Math.round((selected.val ?? 5) * 10)}%`}
              />
              <MetaRow icon={<Tag size={13} />} label="Connections" value={
                String(links.filter(l =>
                  l.source === selected.id ||
                  l.target === selected.id ||
                  (typeof l.source !== 'string' && l.source.id === selected.id) ||
                  (typeof l.target !== 'string' && l.target.id === selected.id)
                ).length)
              } />
            </div>

            {/* Confidence bar */}
            <div>
              <p className="text-[10px] text-muted-foreground font-medium uppercase tracking-wide mb-1">Confidence</p>
              <div className="h-1.5 bg-secondary rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full transition-all duration-500"
                  style={{
                    width: `${Math.min(100, (selected.val ?? 5) * 10)}%`,
                    backgroundColor: meta.color,
                  }}
                />
              </div>
            </div>
          </div>
        )}
      </div>

      <style jsx>{`
        @keyframes slideIn {
          from { opacity: 0; transform: translateX(16px); }
          to   { opacity: 1; transform: translateX(0); }
        }
      `}</style>
    </div>
  );
}

function MetaRow({
  icon,
  label,
  value,
  mono = false,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex items-start gap-2">
      <span className="text-muted-foreground mt-0.5 flex-shrink-0">{icon}</span>
      <div className="flex flex-col min-w-0">
        <span className="text-[10px] text-muted-foreground font-medium uppercase tracking-wide">{label}</span>
        <span className={`text-xs text-gray-700 break-all ${mono ? 'font-mono' : ''}`}>{value}</span>
      </div>
    </div>
  );
}
