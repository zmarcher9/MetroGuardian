import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'
import '@testing-library/jest-dom/vitest'

// RTL's automatic cleanup-after-each-test only self-registers when it detects
// a global `afterEach` (i.e. vitest's `test.globals: true`). We deliberately
// don't enable that globals mode (see vitest.config.ts), so wire it up here.
afterEach(() => {
  cleanup()
})

// jsdom doesn't implement EventSource; App/api.ts use it for live SSE updates.
// A minimal stub is enough for components to construct/close one in tests.
class MockEventSource {
  static instances: MockEventSource[] = []

  url: string
  listeners = new Map<string, Set<(event: MessageEvent) => void>>()
  closed = false

  constructor(url: string) {
    this.url = url
    MockEventSource.instances.push(this)
  }

  addEventListener(type: string, listener: (event: MessageEvent) => void) {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set())
    this.listeners.get(type)!.add(listener)
  }

  removeEventListener(type: string, listener: (event: MessageEvent) => void) {
    this.listeners.get(type)?.delete(listener)
  }

  dispatch(type: string, data: unknown) {
    const event = { data: JSON.stringify(data) } as MessageEvent
    this.listeners.get(type)?.forEach((listener) => listener(event))
  }

  close() {
    this.closed = true
  }
}

// @ts-expect-error - test-only global stub, not a full EventSource implementation
globalThis.EventSource = MockEventSource
export { MockEventSource }
