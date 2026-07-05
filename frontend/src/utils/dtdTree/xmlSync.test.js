import { describe, it, expect } from 'vitest'
import { normalizeElementPathsForTreeSync } from '../xmlPaths'
import { buildNodeFromModel, createNodeIdFactory } from './model'
import { resolveChoiceSelectionsFromXml } from './xmlSync'

describe('resolveChoiceSelectionsFromXml with normalized paths', () => {
  it('picks the branch that matches indexed XML instance paths', () => {
    const nextId = createNodeIdFactory()
    const opts = { rootElement: 'PayDoc', nextId, onRequiredRootCheck: () => {} }

    const model = {
      kind: 'CHOICE',
      children: [
        { kind: 'REF', ref: 'ClientDoc' },
        { kind: 'REF', ref: 'VendorDoc' },
      ],
    }

    const root = buildNodeFromModel({
      name: 'PayDoc',
      model,
      path: 'PayDoc',
      depth: 0,
      required: true,
      ...opts,
    })

    const clientAlt = root.children[0]
    const vendorAlt = root.children[1]

    clientAlt.children = [
      {
        id: 'client-op',
        name: 'operation',
        path: 'PayDoc.ClientDoc.operation',
        isGroupLabel: false,
        children: [],
      },
    ]
    clientAlt._loaded = true

    vendorAlt.children = [
      {
        id: 'vendor-op',
        name: 'operation',
        path: 'PayDoc.VendorDoc.operation',
        isGroupLabel: false,
        children: [],
      },
    ]
    vendorAlt._loaded = true

    const indexedPaths = [
      'PayDoc.ClientDoc.operation[0]',
      'PayDoc.ClientDoc.operation[99]',
      'PayDoc.ClientDoc.operation[0].amount',
    ]
    const syncPaths = normalizeElementPathsForTreeSync(indexedPaths)
    const selections = resolveChoiceSelectionsFromXml(root, new Set(syncPaths))

    expect(selections.get('PayDoc')).toBe('PayDoc.ClientDoc')
  })
})
