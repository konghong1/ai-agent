import { useChatStore } from "./chatStore"

/**
 * StreamManager — module-level singleton that owns the lifecycle of every
 * chat SSE stream, keyed by threadId.
 *
 * Why a singleton (instead of a component ref):
 *   The SSE fetch used to live inside <ChatInterface> and was tied to that
 *   component's lifecycle. Navigating away (or switching threads) unmounted the
 *   component, ran `useEffect` cleanup → `abort()` → the reply died and the
 *   bubble was force-marked "paused". That's exactly the behaviour we want to
 *   kill.
 *
 *   Now each thread gets its own AbortController stored here. Navigation never
 *   aborts a stream — it keeps running in the background and writes the result
 *   into the persisted chat store, so when you come back the bubble is still
 *   `pending` (three-dots waiting animation) or already completed. Only an
 *   explicit user "停止生成" click calls `stopStream`.
 */

const controllers = new Map<string, AbortController>()

/** Register a stream's controller so it survives component unmount. */
export function registerStream(threadId: string, ctrl: AbortController) {
  controllers.set(threadId, ctrl)
  useChatStore.getState().setStreamingThread(threadId, true)
}

/** Remove a stream from the registry (called in the stream's `finally`). */
export function unregisterStream(threadId: string) {
  controllers.delete(threadId)
  useChatStore.getState().setStreamingThread(threadId, false)
}

/** Explicitly stop a single thread's stream (user clicked 停止生成). */
export function stopStream(threadId: string | null | undefined) {
  if (!threadId) return
  const c = controllers.get(threadId)
  if (c) c.abort()
  // The stream's catch/finally will unregister itself.
}

/** True if a stream for this thread is currently in flight. */
export function isStreaming(threadId: string | null | undefined): boolean {
  return !!threadId && controllers.has(threadId)
}
