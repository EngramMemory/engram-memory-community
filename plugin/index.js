import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";

const ENGRAM_VERSION = "1.0.0";

export default definePluginEntry({
  id: "engram",
  name: "Engram Memory",
  description: "Three-Tier Brain memory backend. Your Qdrant, our intelligence.",
  kind: "memory",

  register(api) {
    const cfg = api.pluginConfig || {};
    const apiKey = cfg.apiKey || process.env.ENGRAM_API_KEY || "";
    const apiUrl = cfg.apiUrl || process.env.ENGRAM_API_URL || "https://api.engrammemory.ai";
    const qdrantUrl = cfg.qdrantUrl || process.env.ENGRAM_QDRANT_URL || "http://localhost:6333";
    const embeddingUrl = cfg.embeddingUrl || process.env.ENGRAM_EMBED_URL || "http://localhost:11435";
    const collection = cfg.collection || "agent-memory";
    const autoCapture = cfg.autoCapture !== false;
    const autoRecall = cfg.autoRecall !== false;
    const isCloud = !!apiKey;

    api.logger.info(`engram: registered (${isCloud ? "cloud" : "local"}, qdrant: ${qdrantUrl}, v${ENGRAM_VERSION})`);

    // ── Cloud mode: route through Engram Cloud API ──
    async function cloudFetch(path, method = "GET", body = null) {
      const opts = {
        method,
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${apiKey}`,
          "X-Qdrant-URL": qdrantUrl,
          "X-SDK-Version": `openclaw-plugin/${ENGRAM_VERSION}`,
        },
      };
      if (body) opts.body = JSON.stringify(body);
      const res = await fetch(`${apiUrl}${path}`, opts);
      if (!res.ok) {
        const err = await res.text().catch(() => "");
        throw new Error(`Engram API ${res.status}: ${err}`);
      }
      return res.json();
    }

    // ── Local mode: call FastEmbed + Qdrant directly ──
    async function localEmbed(text) {
      const res = await fetch(`${embeddingUrl}/embeddings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ texts: [text] }),
      });
      if (!res.ok) throw new Error(`FastEmbed ${res.status}`);
      const data = await res.json();
      return data.embeddings[0];
    }

    async function localStore(text, category = "other", importance = 0.5) {
      const vector = await localEmbed(text);
      const id = crypto.randomUUID();
      const res = await fetch(`${qdrantUrl}/collections/${collection}/points`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          points: [{
            id,
            vector,
            payload: { text, content: text, category, importance, timestamp: new Date().toISOString(), access_count: 0 },
          }],
        }),
      });
      if (!res.ok) throw new Error(`Qdrant store ${res.status}`);
      return { id, status: "stored", category, duplicate: false };
    }

    async function localSearch(query, limit = 5) {
      const vector = await localEmbed(query);
      const res = await fetch(`${qdrantUrl}/collections/${collection}/points/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ vector, limit, with_payload: true, score_threshold: 0.3 }),
      });
      if (!res.ok) throw new Error(`Qdrant search ${res.status}`);
      const data = await res.json();
      return (data.result || []).map((hit) => ({
        id: String(hit.id),
        text: hit.payload?.content || hit.payload?.text || "",
        category: hit.payload?.category || "other",
        score: hit.score,
        timestamp: hit.payload?.timestamp || "",
      }));
    }

    async function localForget(memoryId) {
      const res = await fetch(`${qdrantUrl}/collections/${collection}/points/delete`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ points: [memoryId] }),
      });
      return { status: res.ok ? "deleted" : "failed", id: memoryId };
    }

    // ── Tool: memory_store ──
    api.registerTool({
      name: "memory_store",
      label: "Store Memory",
      description: "Store a piece of information in long-term memory. Use for preferences, facts, decisions, and important context.",
      parameters: {
        type: "object",
        properties: {
          text: { type: "string", description: "The information to remember" },
          category: { type: "string", enum: ["preference", "fact", "decision", "entity", "other"], description: "Category of memory" },
          importance: { type: "number", description: "Importance 0-1 (default 0.5)" },
        },
        required: ["text"],
      },
      async execute(_toolCallId, params) {
        const result = isCloud
          ? await cloudFetch("/v1/store", "POST", { text: params.text, category: params.category || "other", importance: params.importance || 0.5 })
          : await localStore(params.text, params.category || "other", params.importance || 0.5);
        return {
          content: [{ type: "text", text: `Stored: "${params.text}" [${result.category}] (id: ${result.id})` }],
          details: result,
        };
      },
    });

    // ── Tool: memory_recall ──
    api.registerTool({
      name: "memory_recall",
      label: "Recall Memory",
      description: "Search through long-term memories. Use when you need context about user preferences, past decisions, or previously discussed topics.",
      parameters: {
        type: "object",
        properties: {
          query: { type: "string", description: "What to search for" },
          limit: { type: "number", description: "Max results (default 5)" },
        },
        required: ["query"],
      },
      async execute(_toolCallId, params) {
        let memories;
        if (isCloud) {
          const result = await cloudFetch("/v1/search", "POST", { query: params.query, limit: params.limit || 5 });
          memories = result.results || [];
        } else {
          memories = await localSearch(params.query, params.limit || 5);
        }

        if (memories.length === 0) {
          return { content: [{ type: "text", text: "No relevant memories found." }], details: { count: 0 } };
        }

        const formatted = memories.map((m, i) => `${i + 1}. [${m.category}] ${m.text} (score: ${m.score?.toFixed(2)})`).join("\n");
        return {
          content: [{ type: "text", text: `Found ${memories.length} memories:\n${formatted}` }],
          details: { count: memories.length, results: memories },
        };
      },
    });

    // ── Tool: memory_forget ──
    api.registerTool({
      name: "memory_forget",
      label: "Forget Memory",
      description: "Remove a specific memory by ID or by searching for it.",
      parameters: {
        type: "object",
        properties: {
          query: { type: "string", description: "Search query to find the memory to forget" },
          memory_id: { type: "string", description: "Specific memory ID to forget" },
        },
      },
      async execute(_toolCallId, params) {
        if (isCloud) {
          const result = await cloudFetch("/v1/forget", "POST", { query: params.query, memory_id: params.memory_id });
          return { content: [{ type: "text", text: result.message || "Memory forgotten." }], details: result };
        }

        // Local: if ID provided, delete directly. If query, search first.
        if (params.memory_id) {
          const result = await localForget(params.memory_id);
          return { content: [{ type: "text", text: `Deleted memory ${params.memory_id}` }], details: result };
        }
        if (params.query) {
          const results = await localSearch(params.query, 1);
          if (results.length === 0) return { content: [{ type: "text", text: "No matching memory found." }] };
          const result = await localForget(results[0].id);
          return { content: [{ type: "text", text: `Deleted: "${results[0].text}"` }], details: result };
        }
        return { content: [{ type: "text", text: "Provide a query or memory_id." }] };
      },
    });

    // ── Auto-recall: inject relevant memories before agent responds ──
    if (autoRecall) {
      api.on("beforeAgentReply", async (ctx) => {
        if (!ctx.userMessage) return;
        try {
          let memories;
          if (isCloud) {
            const result = await cloudFetch("/v1/search", "POST", { query: ctx.userMessage, limit: 5 });
            memories = result.results || [];
          } else {
            memories = await localSearch(ctx.userMessage, 5);
          }
          if (memories.length > 0) {
            const context = memories.map((m) => `[${m.category}] ${m.text}`).join("\n");
            ctx.addSystemContext(`Relevant memories:\n${context}`);
          }
        } catch (err) {
          api.logger.debug(`engram auto-recall failed: ${err.message}`);
        }
      });
    }

    // ── Auto-capture: extract important facts after agent responds ──
    if (autoCapture) {
      api.on("afterAgentReply", async (ctx) => {
        if (!ctx.userMessage || ctx.userMessage.length > 500) return;
        const msg = ctx.userMessage.toLowerCase();
        const patterns = ["i prefer", "i like", "i use", "remember that", "my name is", "i work", "i always", "i never", "we decided"];
        if (!patterns.some((p) => msg.includes(p))) return;

        try {
          if (isCloud) {
            await cloudFetch("/v1/store", "POST", { text: ctx.userMessage, category: "preference", importance: 0.7 });
          } else {
            await localStore(ctx.userMessage, "preference", 0.7);
          }
          api.logger.debug(`engram auto-captured: "${ctx.userMessage.substring(0, 50)}..."`);
        } catch (err) {
          api.logger.debug(`engram auto-capture failed: ${err.message}`);
        }
      });
    }
  },
});
