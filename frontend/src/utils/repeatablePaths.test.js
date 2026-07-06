import { describe, expect, it, vi } from 'vitest'

vi.mock('../api/dtd', () => ({
  getElementTree: vi.fn(),
}))

import { getElementTree } from '../api/dtd'
import { formatRepeatableLabel, loadRepeatablePaths } from './repeatablePaths'

describe('loadRepeatablePaths', () => {
  it('collects + and * element paths from nested models', async () => {
    const models = {
      PayDoc: {
        content_model: {
          kind: 'SEQUENCE',
          children: [
            { kind: 'REF', ref: 'Header' },
            { kind: 'REF', ref: 'Body' },
          ],
        },
      },
      Header: {
        content_model: {
          kind: 'SEQUENCE',
          children: [
            { kind: 'REF', ref: 'Title' },
            { kind: 'REF', ref: 'Meta', quantifier: '*' },
          ],
        },
      },
      Body: {
        content_model: {
          kind: 'REF',
          ref: 'Record',
          quantifier: '+',
        },
      },
      Record: {
        content_model: { kind: 'EMPTY' },
      },
      Title: {
        content_model: { kind: 'PCDATA' },
      },
      Meta: {
        content_model: { kind: 'EMPTY' },
      },
    }

    getElementTree.mockImplementation(async (_schemaId, name) => models[name])

    const paths = await loadRepeatablePaths('schema', 'PayDoc')

    expect(paths.map((p) => p.path)).toEqual([
      'PayDoc.Body.Record',
      'PayDoc.Header.Meta',
    ])
  })

  it('stops at recursive element references', async () => {
    const models = {
      node: {
        content_model: {
          kind: 'SEQUENCE',
          children: [
            { kind: 'REF', ref: 'node', quantifier: '*' },
            { kind: 'REF', ref: 'leaf', quantifier: '+' },
          ],
        },
      },
      leaf: {
        content_model: { kind: 'EMPTY' },
      },
    }

    getElementTree.mockImplementation(async (_schemaId, name) => models[name])

    const paths = await loadRepeatablePaths('schema', 'node')

    expect(paths.map((p) => p.path)).toEqual([
      'node.leaf',
      'node.node',
    ])
  })
})

describe('formatRepeatableLabel', () => {
  it('includes quantifier and path', () => {
    expect(
      formatRepeatableLabel({ name: 'Meta', quantifier: '*', path: 'PayDoc.Header.Meta' }),
    ).toBe('Meta* — PayDoc.Header.Meta')
  })
})
