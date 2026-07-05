const DECLARATION_SCAN_BYTES = 256

const ENCODING_ALIASES = {
  'utf-8': 'utf-8',
  utf8: 'utf-8',
  'windows-1251': 'windows-1251',
  cp1251: 'windows-1251',
  'cp-1251': 'windows-1251',
  'x-cp1251': 'windows-1251',
  'iso-8859-5': 'iso-8859-5',
  'koi8-r': 'koi8-r',
  'koi8-u': 'koi8-u',
}

function normalizeEncodingLabel(raw) {
  const key = raw.trim().toLowerCase().replace(/_/g, '-')
  return ENCODING_ALIASES[key] || key
}

function readEncodingFromDeclaration(bytes) {
  const head = new TextDecoder('latin1').decode(
    bytes.subarray(0, Math.min(bytes.length, DECLARATION_SCAN_BYTES)),
  )
  const match = head.match(/<\?xml\b[^>]*\bencoding\s*=\s*(['"])([^'"]+)\1/i)
  return match ? normalizeEncodingLabel(match[2]) : null
}

function stripBom(bytes) {
  if (bytes.length >= 3 && bytes[0] === 0xef && bytes[1] === 0xbb && bytes[2] === 0xbf) {
    return { bytes: bytes.subarray(3), encoding: 'utf-8' }
  }
  if (bytes.length >= 2 && bytes[0] === 0xff && bytes[1] === 0xfe) {
    return { bytes: bytes.subarray(2), encoding: 'utf-16le' }
  }
  if (bytes.length >= 2 && bytes[0] === 0xfe && bytes[1] === 0xff) {
    return { bytes: bytes.subarray(2), encoding: 'utf-16be' }
  }
  return { bytes, encoding: null }
}

function decodeWithEncoding(bytes, encoding) {
  return new TextDecoder(encoding).decode(bytes)
}

function isValidUtf8(bytes) {
  try {
    new TextDecoder('utf-8', { fatal: true }).decode(bytes)
    return true
  } catch {
    return false
  }
}

function decodeXmlBytes(bytes) {
  const { bytes: withoutBom, encoding: bomEncoding } = stripBom(bytes)
  if (bomEncoding) {
    return decodeWithEncoding(withoutBom, bomEncoding)
  }

  const declared = readEncodingFromDeclaration(withoutBom)
  if (declared) {
    try {
      return decodeWithEncoding(withoutBom, declared)
    } catch {
      // fall through to heuristics below
    }
  }

  if (isValidUtf8(withoutBom)) {
    return decodeWithEncoding(withoutBom, 'utf-8')
  }

  try {
    return decodeWithEncoding(withoutBom, 'windows-1251')
  } catch {
    return decodeWithEncoding(withoutBom, 'utf-8')
  }
}

/** Read an XML file as text, honoring BOM and <?xml encoding="…"?> when present. */
export async function readXmlFileAsText(file) {
  const buffer = await file.arrayBuffer()
  const bytes = new Uint8Array(buffer)
  if (!bytes.length) return ''
  return decodeXmlBytes(bytes)
}
