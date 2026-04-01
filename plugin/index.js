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
    const autoCapture = cfg.autoCapture !== false;
    const autoRecall = cfg.autoRecall !== false;

    api.logger.info(`engram: registered (api: ${apiUrl}, qdrant: ${qdrantUrl}, v${ENGRAM_VERSION})`);

    async function engramFetch(path, method = "GET", body = null) {
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

    // memory_store — save a memory
    api.registerTool({
      name: "memory_store",
      label: "Store Memory",
      description: "Store a piece of information in long-term memory. Use for preferences, facts, decisions, and important context.",
      parameters: {
        type: "object",
        properties: {
          text: { type: "string", description: "The information to remember" },
          category: {
            type: "string",
            enum: ["preference", "fact", "decision", "entity", "other"],
            description: "Category of memory",
          },
          importance: { type: "number", description: "Importance 0-1 (default 0.5)" },
        },
        required: ["text"],
      },
      async execute(_toolCallId, params) {
        const result = await engramFetch("/v1/store", "POST", {
          text: params.text,
          category: params.category || "other",
          importance: params.importance || 0.5,
        });
        return {
          content: [{ type: "text", text: `Stored: "${params.text}" [${result.category}] (id: ${result.id})` }],
          details: result,
        };
      },
    });

    // memory_recall — search memories
    api.registerTool({
      name: "memory_recall",
      label: "Recall Memory",
      description: "Search through long-term memories. Use when you need context about user preferences, past decisions, or previously discussed topics.",
      parameters: {
        type: "object",
        properties: {
          query: { type: "string", description: "What to search for" },
          limit: { type: "number", description: "Max results (default 5)" },
          category: { type: "string", description: "Filter by category" },
        },
        required: ["query"],
      },
      async execute(_toolCallId, params) {
        const result = await engramFetch("/v1/search", "POST", {
          query: params.query,
          limit: params.limit || 5,
          category: params.category,
        });

        const memories = result.results || [];
        if (memories.length === 0) {
          return {
            content: [{ type: "text", text: "No relevant memories found." }],
            details: { count: 0 },
          };
        }

        const formatted = memories
          .map((m, i) => `${i + 1}. [${m.category}] ${m.text} (score: ${m.score?.toFixed(2)})`)
          .join("\n");

        return {
          content: [{ type: "text", text: `Found ${memories.length} memories:\n${formatted}` }],
          details: { count: memories.length, results: memories },
        };
      },
    });

    // memory_forget — delete a memory
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
        const result = await engramFetch("/v1/forget", "POST", {
          query: params.query,
          memory_id: params.memory_id,
        });
        return {
          content: [{ type: "text", text: result.message || "Memory forgotten." }],
          details: result,
        };
      },
    });

    // Auto-recall hook — inject relevant memories before agent responds
    if (autoRecall) {
      api.on("beforeAgentReply", async (ctx) => {
        if (!ctx.userMessage) return;
        try {
          const result = await engramFetch("/v1/search", "POST", {
            query: ctx.userMessage,
            limit: 5,
          });
          const memories = result.results || [];
          if (memories.length > 0) {
            const context = memories
              .map((m) => `[${m.category}] ${m.text}`)
              .join("\n");
            ctx.addSystemContext(`Relevant memories:\n${context}`);
          }
        } catch (err) {
          api.logger.debug(`engram auto-recall failed: ${err.message}`);
        }
      });
    }

    // Auto-capture hook — extract important facts after agent responds
    if (autoCapture) {
      api.on("afterAgentReply", async (ctx) => {
        if (!ctx.userMessage || ctx.userMessage.length > 500) return;
        // Simple heuristic: capture user messages that look like facts/preferences
        const msg = ctx.userMessage.toLowerCase();
        const patterns = ["i prefer", "i like", "i use", "remember that", "my name is", "i work", "i always", "i never", "we decided"];
        const isCaptureable = patterns.some((p) => msg.includes(p));
        if (!isCaptureable) return;

        try {
          await engramFetch("/v1/store", "POST", {
            text: ctx.userMessage,
            category: "preference",
            importance: 0.7,
          });
          api.logger.debug(`engram auto-captured: "${ctx.userMessage.substring(0, 50)}..."`);
        } catch (err) {
          api.logger.debug(`engram auto-capture failed: ${err.message}`);
        }
      });
    }
  },
});
