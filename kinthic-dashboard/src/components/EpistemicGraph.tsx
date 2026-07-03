"use client";

import { useState, useEffect, useRef, useCallback } from 'react';
import dynamic from 'next/dynamic';

// ForceGraph2D uses canvas and window, so it cannot be SSR'd
const ForceGraph2D = dynamic(() => import('react-force-graph-2d'), { ssr: false });

interface GraphNode {
  id: string;
  type: string;
  content: string;
  status: string;
}

interface GraphLink {
  source: string;
  target: string;
  type: string;
}

interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
}

export default function EpistemicGraph() {
  const [data, setData] = useState<GraphData>({ nodes: [], links: [] });
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const graphRef = useRef<any>(null);

  const fetchData = useCallback(async () => {
    try {
      const res = await fetch('http://localhost:8000/api/graph');
      if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
      const json = await res.json();
      
      setData({
        nodes: json.nodes.map((n: any) => ({ ...n, id: n.node_id })),
        links: json.edges.map((e: any) => ({
          source: e.source_node_id,
          target: e.target_node_id,
          type: e.relation_type,
        }))
      });
      setError(null);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 2000);
    return () => clearInterval(interval);
  }, [fetchData]);

  // Handle graph physics setup once after loading
  useEffect(() => {
    if (!loading && !error && graphRef.current) {
      graphRef.current.d3Force('charge').strength(-800);
      graphRef.current.d3Force('link').distance(150);
    }
  }, [loading, error]);

  if (loading) return <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-[#F5A623] text-sm font-medium tracking-widest uppercase animate-pulse">Initializing Topology...</div>;
  if (error) return <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-[#FF453A] text-sm font-medium bg-red-900/20 px-4 py-2 rounded-full border border-red-900/50">Backend Offline: {error}</div>;

  return (
    <div className="w-full h-full relative cursor-crosshair">
      <ForceGraph2D
        ref={graphRef}
        graphData={data}
        nodeRelSize={4}
        nodeColor={(node: any) => {
          if (node.type === 'decision') return '#F5A623';
          if (node.type === 'dead_end') return '#FF453A';
          if (node.type === 'hypothesis') return '#5E5CE6';
          return '#32ADE6'; // Fact
        }}
        linkColor={() => '#6272A4'}
        linkWidth={1.5}
        linkDirectionalArrowLength={5}
        linkDirectionalArrowRelPos={1}
        nodeCanvasObject={(node: any, ctx: any, globalScale: number) => {
          // Create label from content
          const maxLen = 35;
          const content = node.content || node.type;
          const label = content.length > maxLen ? content.substring(0, maxLen) + "..." : content;
          
          const fontSize = 12 / globalScale;
          ctx.font = `600 ${fontSize}px "Inter", -apple-system, sans-serif`;
          
          const textWidth = ctx.measureText(label).width;
          const bgWidth = textWidth + (16 / globalScale);
          const bgHeight = fontSize + (12 / globalScale);
          const radius = 4 / globalScale;

          // Get color based on type
          const color = node.type === 'decision' ? '#F5A623' : 
                        node.type === 'dead_end' ? '#FF453A' : 
                        node.type === 'hypothesis' ? '#5E5CE6' : '#32ADE6';

          // Draw pill background
          ctx.fillStyle = 'rgba(15, 15, 20, 0.9)';
          ctx.beginPath();
          
          if (ctx.roundRect) {
              ctx.roundRect(node.x - bgWidth / 2, node.y - bgHeight / 2, bgWidth, bgHeight, radius);
          } else {
              ctx.rect(node.x - bgWidth / 2, node.y - bgHeight / 2, bgWidth, bgHeight);
          }
          
          ctx.fill();
          
          // Draw border
          ctx.strokeStyle = color;
          ctx.lineWidth = 1.5 / globalScale;
          ctx.stroke();
          
          // Draw text
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.fillStyle = '#FFFFFF';
          ctx.fillText(label, node.x, node.y);
          
          // Add a small type badge above
          const typeLabel = node.type.toUpperCase();
          ctx.font = `800 ${fontSize * 0.65}px "Inter", -apple-system, sans-serif`;
          ctx.fillStyle = color;
          ctx.fillText(typeLabel, node.x, node.y - (bgHeight/2) - (6/globalScale));
        }}
        enableNodeDrag={true}
        enableZoomInteraction={true}
        enablePanInteraction={true}
      />
    </div>
  );
}
