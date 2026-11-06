/**
 * Proxyflare JS worker. Behaviour is defined in docs/worker-contract.md.
 * Based on FlareProx by MrTurvey: https://github.com/MrTurvey/flareprox
 */
const KEY_HEADER = 'X-Proxyflare-Key'
const ERROR_HEADER = 'X-Proxyflare-Error'

const ROUTING_PARAMS = new Set(['url', '_cb', '_t'])

const BLOCKED_REQUEST_HEADERS = new Set([
    'host',
    'x-proxyflare-key', 'x-target-url', 'x-my-x-forwarded-for',
    'x-forwarded-for', 'x-forwarded-proto', 'x-forwarded-host', 'x-real-ip',
    'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
    'te', 'trailer', 'transfer-encoding', 'upgrade', 'content-length'
])

const BLOCKED_RESPONSE_HEADERS = new Set(['content-encoding', 'content-length', 'transfer-encoding'])

const CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS, PATCH, HEAD',
    'Access-Control-Allow-Headers': '*'
}

export default {
    async fetch(request, env) {
        if (request.method === 'OPTIONS') {
            return new Response(null, { status: 204, headers: CORS_HEADERS })
        }

        if (!isValidKey(request.headers.get(KEY_HEADER), env.PROXYFLARE_KEY)) {
            return createErrorResponse('Unauthorized', 401)
        }

        const requestUrl = new URL(request.url)
        const rawTarget = getRawTarget(requestUrl, request.headers)
        if (!rawTarget) {
            return createErrorResponse('No target URL specified', 400)
        }

        const targetUrl = buildTargetUrl(requestUrl, rawTarget)
        if (!targetUrl) {
            return createErrorResponse('Invalid target URL', 400)
        }

        try {
            const response = await fetch(createProxyRequest(request, targetUrl))
            return createProxyResponse(response)
        } catch (error) {
            console.error('Proxy request failed:', error)
            return createErrorResponse('Proxy request failed', 502)
        }
    }
}

function isValidKey(providedKey, expectedKey) {
    if (!providedKey || !expectedKey) return false

    const encoder = new TextEncoder()
    const provided = encoder.encode(providedKey)
    const expected = encoder.encode(expectedKey)
    return provided.byteLength === expected.byteLength && crypto.subtle.timingSafeEqual(provided, expected)
}

function getRawTarget(requestUrl, headers) {
    const fromQuery = requestUrl.searchParams.get('url')
    if (fromQuery) return fromQuery

    const fromHeader = headers.get('X-Target-URL')
    if (fromHeader) return fromHeader

    const fromPath = requestUrl.pathname.slice(1)
    return /^https?:\/\//.test(fromPath) ? fromPath : null
}

function buildTargetUrl(requestUrl, rawTarget) {
    let targetUrl
    try {
        targetUrl = new URL(rawTarget)
    } catch {
        return null
    }
    if (!['http:', 'https:'].includes(targetUrl.protocol)) return null

    for (const [key, value] of requestUrl.searchParams) {
        if (!ROUTING_PARAMS.has(key)) targetUrl.searchParams.append(key, value)
    }
    return targetUrl
}

function isForwardableHeader(name) {
    const lowerName = name.toLowerCase()
    return !BLOCKED_REQUEST_HEADERS.has(lowerName) && !lowerName.startsWith('cf-')
}

function createProxyRequest(request, targetUrl) {
    const headers = new Headers()
    for (const [name, value] of request.headers) {
        if (isForwardableHeader(name)) headers.append(name, value)
    }
    headers.set('X-Forwarded-For', request.headers.get('X-My-X-Forwarded-For') ?? generateRandomIp())

    return new Request(targetUrl, {
        method: request.method,
        headers,
        body: ['GET', 'HEAD'].includes(request.method) ? null : request.body
    })
}

function createProxyResponse(response) {
    const headers = new Headers()
    for (const [name, value] of response.headers) {
        // append, not set: a response can carry several Set-Cookie headers
        if (!BLOCKED_RESPONSE_HEADERS.has(name.toLowerCase())) headers.append(name, value)
    }
    for (const [name, value] of Object.entries(CORS_HEADERS)) {
        headers.set(name, value)
    }

    return new Response(response.body, {
        status: response.status,
        statusText: response.statusText,
        headers
    })
}

function createErrorResponse(message, status) {
    return new Response(JSON.stringify({ error: message }), {
        status,
        headers: { 'Content-Type': 'application/json', [ERROR_HEADER]: 'true', ...CORS_HEADERS }
    })
}

function generateRandomIp() {
    return Array.from({ length: 4 }, () => Math.floor(Math.random() * 255) + 1).join('.')
}
