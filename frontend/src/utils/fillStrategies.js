export const FILL_STRATEGIES = {
  AI: 'ai',
  DB_AI: 'db_ai',
  GIT_AI: 'git_ai',
  GIT_AI_DB: 'git_ai_db',
}

export const DB_FILL_STRATEGIES = new Set([FILL_STRATEGIES.DB_AI, FILL_STRATEGIES.GIT_AI_DB])

export function usesDbFill(strategy) {
  return DB_FILL_STRATEGIES.has(strategy)
}

export function usesLlmFill(strategy) {
  return Object.values(FILL_STRATEGIES).includes(strategy)
}
