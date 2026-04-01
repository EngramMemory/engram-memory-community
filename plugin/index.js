import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";

const ENGRAM_VERSION = "1.0.1";

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

    // ═══════════════════════════════════════════════════════════════
    // Engram Cloud API — stateless intelligence, never writes to
    // the customer's Qdrant. Returns vectors + metadata only.
    // ═══════════════════════════════════════════════════════════════

    async function cloudIntelligence(text) {
      const res = await fetch(`${apiUrl}/v1/intelligence`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${apiKey}`,
          "X-SDK-Version": `openclaw-plugin/${ENGRAM_VERSION}`,
        },
        body: JSON.stringify({ text }),
      });
      if (!res.ok) throw new Error(`Engram intelligence ${res.status}`);
      return res.json();
      // Returns: { vector, dimension, category, tokens_used, dedup, compressed_vector, ... }
    }

    async function cloudOverflowSearch(vector, limit = 5) {
      const res = await fetch(`${apiUrl}/v1/overflow/search`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${apiKey}`,
          "X-SDK-Version": `openclaw-plugin/${ENGRAM_VERSION}`,
        },
        body: JSON.stringify({ vector, limit }),
      });
      if (!res.ok) return []; // Overflow unavailable is not fatal
      const data = await res.json();
      return (data.results || []).map((r) => ({ ...r, tier: "overflow" }));
    }

    // ═══════════════════════════════════════════════════════════════
    // Local Qdrant + FastEmbed — all reads and writes happen here.
    // In cloud mode, Engram provides the vectors; we still write.
    // ═══════════════════════════════════════════════════════════════

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

    async function getVector(text) {
      // Cloud: Engram generates the vector (better dedup, classification)
      // Local: FastEmbed generates the vector
      if (isCloud) {
        const intel = await cloudIntelligence(text);
        return { vector: intel.vector, category: intel.category || "other", dedup: intel.dedup };
      }
      const vector = await localEmbed(text);
      return { vector, category: "other", dedup: null };
    }

    async function qdrantWrite(id, vector, payload) {
      const res = await fetch(`${qdrantUrl}/collections/${collection}/points`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ points: [{ id, vector, payload }] }),
      });
      if (!res.ok) throw new Error(`Qdrant write ${res.status}`);
    }

    async function qdrantSearch(vector, limit = 5) {
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
        tier: "local",
      }));
    }

    async function qdrantDelete(memoryId) {
      const res = await fetch(`${qdrantUrl}/collections/${collection}/points/delete`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ points: [memoryId] }),
      });
      return res.ok;
    }

    // ═══════════════════════════════════════════════════════════════
    // Tools — the agent interface
    // ═══════════════════════════════════════════════════════════════

    // memory_store: get intelligence from Engram (or local embed),
    // then write to YOUR Qdrant. Engram never touches your storage.
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
        const { vector, category, dedup } = await getVector(params.text);

        // Dedup: if Engram says this is a duplicate, skip the write
        if (dedup?.is_duplicate) {
          return {
            content: [{ type: "text", text: `Duplicate detected — similar memory already exists (similarity: ${dedup.similarity?.toFixed(2)})` }],
            details: { duplicate: true, similarity: dedup.similarity },
          };
        }

        const id = crypto.randomUUID();
        const resolvedCategory = params.category || category || "other";
        const payload = {
          text: params.text,
          content: params.text,
          category: resolvedCategory,
          importance: params.importance || 0.5,
          timestamp: new Date().toISOString(),
          access_count: 0,
        };

        // Plugin writes to local Qdrant — Engram never does
        await qdrantWrite(id, vector, payload);

        return {
          content: [{ type: "text", text: `Stored: "${params.text}" [${resolvedCategory}] (id: ${id})` }],
          details: { id, status: "stored", category: resolvedCategory, duplicate: false },
        };
      },
    });

    // memory_recall: search local Qdrant first, spill into overflow
    // if cloud mode is active and local results are insufficient.
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
        const limit = params.limit || 5;
        const { vector } = await getVector(params.query);

        // L1: search local Qdrant
        let memories = await qdrantSearch(vector, limit);

        // L2: if cloud mode and local didn't fill the limit, search overflow
        if (isCloud && memories.length < limit) {
          try {
            const overflow = await cloudOverflowSearch(vector, limit - memories.length);
            const localIds = new Set(memories.map((m) => m.id));
            const unique = overflow.filter((m) => !localIds.has(m.id));
            memories = [...memories, ...unique];
          } catch (err) {
            api.logger.debug(`engram overflow search failed: ${err.message}`);
          }
        }

        // Sort by score descending, take limit
        memories.sort((a, b) => (b.score || 0) - (a.score || 0));
        memories = memories.slice(0, limit);

        if (memories.length === 0) {
          return { content: [{ type: "text", text: "No relevant memories found." }], details: { count: 0 } };
        }

        const formatted = memories
          .map((m, i) => `${i + 1}. [${m.category}] ${m.text} (${m.score?.toFixed(2)}, ${m.tier || "local"})`)
          .join("\n");

        return {
          content: [{ type: "text", text: `Found ${memories.length} memories:\n${formatted}` }],
          details: { count: memories.length, results: memories },
        };
      },
    });

    // memory_forget: delete from local Qdrant. Engram never deletes
    // from your storage — the plugin does.
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
        if (params.memory_id) {
          const ok = await qdrantDelete(params.memory_id);
          return {
            content: [{ type: "text", text: ok ? `Deleted memory ${params.memory_id}` : "Delete failed" }],
            details: { status: ok ? "deleted" : "failed", id: params.memory_id },
          };
        }
        if (params.query) {
          const { vector } = await getVector(params.query);
          const results = await qdrantSearch(vector, 1);
          if (results.length === 0) {
            return { content: [{ type: "text", text: "No matching memory found." }] };
          }
          const ok = await qdrantDelete(results[0].id);
          return {
            content: [{ type: "text", text: ok ? `Deleted: "${results[0].text}"` : "Delete failed" }],
            details: { status: ok ? "deleted" : "failed", id: results[0].id },
          };
        }
        return { content: [{ type: "text", text: "Provide a query or memory_id." }] };
      },
    });

    // ═══════════════════════════════════════════════════════════════
    // Auto-recall: inject relevant memories before agent responds
    // Searches local first, spills into overflow if cloud mode.
    // ═══════════════════════════════════════════════════════════════

    if (autoRecall) {
      api.on("beforeAgentReply", async (ctx) => {
        if (!ctx.userMessage) return;
        try {
          const { vector } = await getVector(ctx.userMessage);
          let memories = await qdrantSearch(vector, 5);

          if (isCloud && memories.length < 3) {
            try {
              const overflow = await cloudOverflowSearch(vector, 5 - memories.length);
              const localIds = new Set(memories.map((m) => m.id));
              memories = [...memories, ...overflow.filter((m) => !localIds.has(m.id))];
            } catch {}
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

    // ═══════════════════════════════════════════════════════════════
    // Auto-capture: extract important facts after agent responds
    // Uses getVector (cloud intelligence or local embed) then writes
    // to local Qdrant. Engram never writes to your storage.
    // ═══════════════════════════════════════════════════════════════

    if (autoCapture) {
      api.on("afterAgentReply", async (ctx) => {
        if (!ctx.userMessage || ctx.userMessage.length > 500) return;
        const msg = ctx.userMessage.toLowerCase();
        const patterns = ["i prefer", "i like", "i use", "remember that", "my name is", "i work", "i always", "i never", "we decided"];
        if (!patterns.some((p) => msg.includes(p))) return;

        try {
          const { vector, category } = await getVector(ctx.userMessage);
          const id = crypto.randomUUID();
          await qdrantWrite(id, vector, {
            text: ctx.userMessage,
            content: ctx.userMessage,
            category: category || "preference",
            importance: 0.7,
            timestamp: new Date().toISOString(),
            access_count: 0,
          });
          api.logger.debug(`engram auto-captured: "${ctx.userMessage.substring(0, 50)}..."`);
        } catch (err) {
          api.logger.debug(`engram auto-capture failed: ${err.message}`);
        }
      });
    }
  },
});
