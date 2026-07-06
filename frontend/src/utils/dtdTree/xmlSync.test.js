import { describe, it, expect } from 'vitest'
import { normalizeElementPathsForTreeSync } from '../xmlPaths'
import {
  buildNodeFromModel,
  collectDirectChildNamesFromXmlPaths,
  createNodeIdFactory,
  injectXmlChildrenIntoAnyNode,
} from './model'
import { buildCheckedPathsFromElementPaths, resolveChoiceSelectionsFromXml } from './xmlSync'

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

describe('ANY content from pasted XML', () => {
  const nextId = createNodeIdFactory()
  const modelOptions = () => ({
    rootElement: 'Wrapper',
    nextId,
    onRequiredRootCheck: () => {},
  })

  it('collects direct child names under an ANY parent path', () => {
    const paths = [
      'Wrapper',
      'Wrapper.Section',
      'Wrapper.Section.Item',
      'Wrapper.Note',
    ]
    expect(collectDirectChildNamesFromXmlPaths('Wrapper', paths)).toEqual(['Note', 'Section'])
    expect(collectDirectChildNamesFromXmlPaths('Wrapper.Section', paths)).toEqual(['Item'])
  })

  it('injects children into an ANY node and syncs checked paths', async () => {
    const root = buildNodeFromModel({
      name: 'Wrapper',
      model: { kind: 'ANY' },
      path: 'Wrapper',
      depth: 0,
      required: true,
      ...modelOptions(),
    })

    const elementPaths = [
      'Wrapper',
      'Wrapper.Section',
      'Wrapper.Section.Item',
      'Wrapper.Note',
    ]
    const syncPaths = normalizeElementPathsForTreeSync(elementPaths)

    const getElementTree = async (name) => {
      if (name === 'Section') {
        return { content_model: { kind: 'SEQUENCE', children: [{ kind: 'REF', ref: 'Item' }] } }
      }
      if (name === 'Note') return { content_model: { kind: 'EMPTY' } }
      if (name === 'Item') return { content_model: { kind: 'EMPTY' } }
      return { content_model: { kind: 'ANY' } }
    }

    const checked = await buildCheckedPathsFromElementPaths({
      elementPaths,
      treeRoot: root,
      getElementTree,
      isStale: () => false,
      preferPaths: new Set(),
      modelOptions: modelOptions(),
    })

    expect(root.hasChildren).toBe(true)
    expect(root.children.map((n) => n.name)).toEqual(['Note', 'Section'])

    const section = root.children.find((n) => n.name === 'Section')
    expect(section?.children?.some((n) => n.name === 'Item')).toBe(true)

    expect([...checked].map((p) => normalizeElementPathsForTreeSync([p])[0]).sort()).toEqual(
      [...syncPaths].sort(),
    )
  })

  it('injects only immediate children for nested ANY containers', () => {
    const container = buildNodeFromModel({
      name: 'Body',
      model: { kind: 'ANY' },
      path: 'Doc.Body',
      depth: 1,
      required: false,
      ...modelOptions(),
    })

    injectXmlChildrenIntoAnyNode(
      container,
      ['Doc.Body.Block', 'Doc.Body.Block.Line', 'Doc.Body.Footer'],
      modelOptions(),
    )

    expect(container.children.map((n) => n.name)).toEqual(['Block', 'Footer'])
    const block = container.children.find((n) => n.name === 'Block')
    expect(block?.hasChildren).toBe(true)
    expect(block?.children).toEqual([])
  })
})
