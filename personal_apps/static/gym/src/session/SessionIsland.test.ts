import { QueryClient } from '@tanstack/react-query'
import { describe, expect, it } from 'vitest'
import { writesSettled } from './SessionIsland'
import { sessionKey } from './useSessionMutation'

/** Finishing waits on this. It used to navigate with a set still on its way,
 *  and the form post won the race: the set never reached the workout. */
describe('writesSettled', () => {
  const key = sessionKey(7)

  it('resolves at once when nothing is in flight', async () => {
    const client = new QueryClient()
    await expect(writesSettled(client, key)).resolves.toBeUndefined()
  })

  it('waits for every write in the queue, not only the first', async () => {
    const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } })
    const answers: (() => void)[] = []
    const write = () => client.getMutationCache().build(client, {
      mutationKey: key,
      scope: { id: 'session-7' },
      mutationFn: () => new Promise<void>((resolve) => { answers.push(resolve) }),
    }).execute(undefined)

    void write()
    void write()
    let settled = false
    void writesSettled(client, key).then(() => { settled = true })

    await Promise.resolve()
    answers.shift()!()
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(settled).toBe(false)

    // The second one only starts once the first has answered.
    await new Promise((resolve) => setTimeout(resolve, 0))
    answers.shift()!()
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(settled).toBe(true)
  })
})
