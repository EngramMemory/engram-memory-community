/**
 * Engram Memory Community Edition — OpenClaw Plugin Entry Point
 *
 * Provides persistent semantic memory via Qdrant + FastEmbed.
 * Hooks into OpenClaw's agent lifecycle for auto-recall and auto-capture.
 */

import { v4 as uuidv4 } from "uuid";

// ─── Types ──────────────────────────────────────────────────────────

interface PluginConfig {
  qdrantUrl: string;
  embeddingUrl: string;
  embeddingModel: string;
  embeddingDimension: number;
  autoRecall: boolean;
  autoCapture: boolean;
  maxRecallResults: number;
  minRecallScore: number;
  debug: boolean;
}

interface Memory {
  id: string;
  text: string;
  category: string;
  importance: number;
  timestamp: string;
  tags: string[];
}

interface QdrantPoint {
  id: string;
  vector: number[];
  payload: Record<string, unknown>;
}

interface QdrantSearchResult {
  id: string;
  score: number;
  payload: Record<string, unknown>;
}

// ─── Defaults ───────────────────────────────────────────────────────

const DEFAULT_CONFIG: PluginConfig = {
  qdrantUrl: "http://localhost:6333",
  embeddingUrl: "http://localhost:11435",
  embeddingModel: "nomic-ai/nomic-embed-text-v1.5",
  embeddingDimension: 768,
  autoRecall: true,
  autoCapture: true,
  maxRecallResults: 5,
  minRecallScore: 0.35,
  debug: false,
};

// Short messages that don't warrant memory operations
const SKIP_PATTERNS = /^(hi|hey|hello|ok|okay|thanks|ty|yes|no|sure|yep|nah|k|lol|haha|hmm|huh|bye|gn|gm|yo|sup)[\s!?.]*$/i;

// Category detection patterns
const CATEGORY_PATTERNS: Record<string, RegExp> = {
  preference: /\b(prefer|like|always|never|want|love|hate|enjoy|favor|rather)\b/i,
  decision: /\b(decided|chosen|selected|will use|going with|switched to|moved to|picking)\b/i,
  fact: /\b(completed|version|status|count|running|deployed|migrated|installed|updated|is at|currently)\b/i,
  entity: /\b(company|team|person|project|service|app|platform|organization)\b/i,
};

// ─── Plugin Class ───────────────────────────────────────────────────

class EngramMemoryPlugin {
  private config: PluginConfig;
  private messageCount = 0;
  private readonly COLLECTION_NAME = "agent-memory";

  constructor(userConfig: Partial<PluginConfig> = {}) {
    this.config = { ...DEFAULT_CONFIG, ...userConfig };
    
    console.log("[engram-memory] Engram Community Edition initialized");
  }

  private log(...args: unknown[]) {
    if (this.config.debug) {
      console.log("[engram-memory]", ...args);
    }
  }

  // ─── Embedding ──────────────────────────────────────────────────

  private async embed(text: string): Promise<number[]> {
    const res = await fetch(`${this.config.embeddingUrl}/api/embed`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model: this.config.embeddingModel,
        input: text,
      }),
    });

    if (!res.ok) {
      throw new Error(`Embedding failed: ${res.status} ${await res.text()}`);
    }

    const data = await res.json();

    // Handle both Ollama-style and FastEmbed-style responses
    if (data.embeddings) return data.embeddings[0];
    if (data.embedding) return data.embedding;
    if (Array.isArray(data) && Array.isArray(data[0])) return data[0];
    if (Array.isArray(data)) return data;

    throw new Error("Unexpected embedding response format");
  }

  // ─── Qdrant Operations ─────────────────────────────────────────

  private async ensureCollection(): Promise<void> {
    const url = `${this.config.qdrantUrl}/collections/${this.COLLECTION_NAME}`;
    const check = await fetch(url);

    if (check.status === 404) {
      this.log("Creating collection:", this.COLLECTION_NAME);
      const res = await fetch(url, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          vectors: {
            size: this.config.embeddingDimension,
            distance: "Cosine",
          },
          quantization_config: {
            scalar: {
              type: "int8",
              quantile: 0.99,
              always_ram: false
            }
          }
        }),
      });
      if (!res.ok) {
        throw new Error(`Failed to create collection: ${await res.text()}`);
      }
    }
  }

  private async upsertPoint(point: QdrantPoint): Promise<void> {
    const url = `${this.config.qdrantUrl}/collections/${this.COLLECTION_NAME}/points`;
    const res = await fetch(url, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ points: [point] }),
    });
    if (!res.ok) {
      throw new Error(`Qdrant upsert failed: ${await res.text()}`);
    }
  }

  private async searchPoints(
    vector: number[],
    limit: number,
    filter?: Record<string, unknown>
  ): Promise<QdrantSearchResult[]> {
    const url = `${this.config.qdrantUrl}/collections/${this.COLLECTION_NAME}/points/search`;
    const body: Record<string, unknown> = {
      vector,
      limit,
      with_payload: true,
      score_threshold: this.config.minRecallScore,
    };
    if (filter) body.filter = filter;

    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      throw new Error(`Qdrant search failed: ${await res.text()}`);
    }

    const data = await res.json();
    return data.result || [];
  }

  private async deletePoint(id: string): Promise<void> {
    const url = `${this.config.qdrantUrl}/collections/${this.COLLECTION_NAME}/points/delete`;
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ points: [id] }),
    });
    if (!res.ok) {
      throw new Error(`Qdrant delete failed: ${await res.text()}`);
    }
  }

  private async scrollPoints(
    limit: number,
    filter?: Record<string, unknown>,
    offset?: string
  ): Promise<{ points: QdrantSearchResult[]; next_page_offset?: string }> {
    const url = `${this.config.qdrantUrl}/collections/${this.COLLECTION_NAME}/points/scroll`;
    const body: Record<string, unknown> = { limit, with_payload: true, with_vector: false };
    if (filter) body.filter = filter;
    if (offset) body.offset = offset;

    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`Qdrant scroll failed: ${await res.text()}`);

    const data = await res.json();
    return { points: data.result?.points || [], next_page_offset: data.result?.next_page_offset };
  }

  // ─── Category Detection ─────────────────────────────────────────

  private detectCategory(text: string): string {
    for (const [category, pattern] of Object.entries(CATEGORY_PATTERNS)) {
      if (pattern.test(text)) return category;
    }
    return "other";
  }

  // ─── Tool Handlers ──────────────────────────────────────────────

  async memoryStore(
    text: string,
    category?: string,
    importance?: number
  ): Promise<string> {
    await this.ensureCollection();
    const vector = await this.embed(text);

    const id = uuidv4();
    const resolvedCategory = category || this.detectCategory(text);
    const now = new Date().toISOString();

    await this.upsertPoint({
      id,
      vector,
      payload: {
        text,
        category: resolvedCategory,
        importance: importance ?? 0.5,
        timestamp: now,
        tags: [],
      },
    });

    this.log("Stored memory:", id, resolvedCategory);
    return `Memory stored [${resolvedCategory}]: ${text.substring(0, 80)}...`;
  }

  async memorySearch(
    query: string,
    limit?: number,
    category?: string,
    minImportance?: number
  ): Promise<Memory[]> {
    await this.ensureCollection();
    const vector = await this.embed(query);

    // Build Qdrant filter
    let filter: Record<string, unknown> | undefined;
    const mustClauses: Record<string, unknown>[] = [];

    if (category) {
      mustClauses.push({ key: "category", match: { value: category } });
    }
    if (minImportance !== undefined) {
      mustClauses.push({ key: "importance", range: { gte: minImportance } });
    }
    if (mustClauses.length > 0) {
      filter = { must: mustClauses };
    }

    const results = await this.searchPoints(
      vector,
      limit || this.config.maxRecallResults,
      filter
    );

    return results.map((r) => ({
      id: r.id,
      text: r.payload.text as string,
      category: r.payload.category as string,
      importance: r.payload.importance as number,
      timestamp: r.payload.timestamp as string,
      tags: (r.payload.tags as string[]) || [],
    }));
  }

  async memoryList(
    limit?: number,
    category?: string
  ): Promise<Memory[]> {
    await this.ensureCollection();

    let filter: Record<string, unknown> | undefined;
    if (category) {
      filter = { must: [{ key: "category", match: { value: category } }] };
    }

    const result = await this.scrollPoints(limit || 10, filter);

    return result.points.map((p) => ({
      id: p.id,
      text: p.payload.text as string,
      category: p.payload.category as string,
      importance: p.payload.importance as number,
      timestamp: p.payload.timestamp as string,
      tags: (p.payload.tags as string[]) || [],
    }));
  }

  async memoryForget(memoryId?: string, query?: string): Promise<string> {
    if (memoryId) {
      await this.deletePoint(memoryId);
      return `Memory ${memoryId} deleted.`;
    }
    if (query) {
      const results = await this.memorySearch(query, 1);
      if (results.length === 0) return "No matching memory found.";
      await this.deletePoint(results[0].id);
      return `Deleted: "${results[0].text.substring(0, 60)}..."`;
    }
    return "Provide either memoryId or query to forget.";
  }

  // ─── Auto-Capture: Extract facts from conversation ──────────────

  private extractFacts(userMessage: string, agentResponse: string): string[] {
    const facts: string[] = [];
    const combined = `${userMessage}\n${agentResponse}`;
    const sentences = combined.split(/[.!?\n]+/).map((s) => s.trim()).filter((s) => s.length > 20);

    for (const sentence of sentences) {
      // Skip questions, generic filler, and very long sentences
      if (sentence.endsWith("?")) continue;
      if (sentence.length > 300) continue;
      if (/^(I think|maybe|perhaps|probably|might|could be)/i.test(sentence)) continue;

      // Keep sentences that match category patterns (strong signals)
      for (const pattern of Object.values(CATEGORY_PATTERNS)) {
        if (pattern.test(sentence)) {
          facts.push(sentence);
          break;
        }
      }
    }

    return facts.slice(0, 3); // Cap at 3 facts per turn to avoid noise
  }

  // ─── OpenClaw Lifecycle Hooks ───────────────────────────────────

  /**
   * before_agent_start — runs before the LLM generates a response.
   * Searches for relevant memories and injects them as context.
   */
  async beforeAgentStart(context: {
    userMessage: string;
    prependContext?: string;
  }): Promise<{ prependContext?: string }> {
    if (!this.config.autoRecall) return {};

    const msg = context.userMessage?.trim();
    if (!msg || SKIP_PATTERNS.test(msg)) return {};

    try {
      const memories = await this.memorySearch(msg, this.config.maxRecallResults);

      if (memories.length === 0) return {};

      const memoryBlock = memories
        .map((m) => `- [${m.category}] ${m.text}`)
        .join("\n");

      const injection = `\n<recalled_memories>\nThe following are relevant memories from past sessions:\n${memoryBlock}\n</recalled_memories>\n`;

      this.log(`Auto-recalled ${memories.length} memories`);

      return { prependContext: injection };
    } catch (e) {
      this.log("Auto-recall failed:", e);
      return {};
    }
  }

  /**
   * after_agent_response — runs after the LLM responds.
   * Extracts important facts and stores them.
   */
  async afterAgentResponse(context: {
    userMessage: string;
    agentResponse: string;
  }): Promise<void> {
    this.messageCount++;

    // Auto-capture
    if (this.config.autoCapture) {
      const msg = context.userMessage?.trim();
      if (msg && !SKIP_PATTERNS.test(msg)) {
        try {
          const facts = this.extractFacts(context.userMessage, context.agentResponse);
          for (const fact of facts) {
            await this.memoryStore(fact);
          }
          if (facts.length > 0) {
            this.log(`Auto-captured ${facts.length} facts`);
          }
        } catch (e) {
          this.log("Auto-capture failed:", e);
        }
      }
    }

  }
}

// ─── Plugin Registration (OpenClaw entry point) ───────────────────

let plugin: EngramMemoryPlugin;

export function register(config: Partial<PluginConfig> = {}) {
  plugin = new EngramMemoryPlugin(config);
  
  console.log("[engram-memory] Community Edition registered — collection: agent-memory");

  return {
    // ── Lifecycle Hooks ──────────────────────────────────────────
    hooks: {
      before_agent_start: async (ctx: { userMessage: string; prependContext?: string }) => {
        return plugin.beforeAgentStart(ctx);
      },
      after_agent_response: async (ctx: { userMessage: string; agentResponse: string }) => {
        return plugin.afterAgentResponse(ctx);
      },
    },

    // ── Tool Implementations ─────────────────────────────────────
    tools: {
      memory_store: async (params: { text: string; category?: string; importance?: number }) => {
        return plugin.memoryStore(params.text, params.category, params.importance);
      },
      memory_search: async (params: { query: string; limit?: number; category?: string; minImportance?: number }) => {
        const results = await plugin.memorySearch(params.query, params.limit, params.category, params.minImportance);
        if (results.length === 0) return "No memories found.";
        return results
          .map((m, i) => `${i + 1}. [${m.category}] (importance: ${m.importance.toFixed(2)}) ${m.text}`)
          .join("\n");
      },
      memory_list: async (params: { limit?: number; category?: string }) => {
        const results = await plugin.memoryList(params.limit, params.category);
        if (results.length === 0) return "No memories stored yet.";
        return results
          .map((m, i) => `${i + 1}. [${m.category}] ${m.text} (${m.timestamp})`)
          .join("\n");
      },
      memory_forget: async (params: { memoryId?: string; query?: string }) => {
        return plugin.memoryForget(params.memoryId, params.query);
      },
      memory_profile: async (params: { action?: string; key?: string; value?: string; scope?: string }) => {
        if (params.action === "view" || !params.action) {
          const profiles = await plugin.memorySearch("user profile preferences", 20);
          const profileMemories = profiles.filter((m) => m.category === "preference" || m.tags?.includes("profile"));
          if (profileMemories.length === 0) return "No profile data stored yet.";
          return profileMemories.map((m) => `- ${m.text}`).join("\n");
        }
        if (params.action === "add" && params.key && params.value) {
          const text = `[profile:${params.scope || "static"}] ${params.key}: ${params.value}`;
          return plugin.memoryStore(text, "preference", 0.9);
        }
        if (params.action === "remove" && params.key) {
          return plugin.memoryForget(undefined, `profile ${params.key}`);
        }
        return "Usage: memory_profile(action='view|add|remove', key, value, scope)";
      },
    },
  };
}

export default { register };