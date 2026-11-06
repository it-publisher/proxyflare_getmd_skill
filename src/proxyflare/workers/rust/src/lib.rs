//! Proxyflare Rust worker. Behaviour is defined in docs/worker-contract.md.

use url::Url;
use worker::*;

mod utils;

const KEY_HEADER: &str = "X-Proxyflare-Key";
const KEY_BINDING: &str = "PROXYFLARE_KEY";
const ERROR_HEADER: &str = "X-Proxyflare-Error";

const ROUTING_PARAMS: &[&str] = &["url", "_cb", "_t"];

const BLOCKED_REQUEST_HEADERS: &[&str] = &[
    "host",
    "x-proxyflare-key",
    "x-target-url",
    "x-my-x-forwarded-for",
    "x-forwarded-for",
    "x-forwarded-proto",
    "x-forwarded-host",
    "x-real-ip",
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
    "content-length",
];

const BLOCKED_RESPONSE_HEADERS: &[&str] = &["content-encoding", "content-length", "transfer-encoding"];

const NULL_BODY_STATUSES: &[u16] = &[101, 204, 205, 304];

/// The seed is a parameter because `Date::now` only works on wasm, which native tests can't use.
fn generate_random_ip(seed: u64) -> String {
    let mut state = seed;

    // Simple Linear Congruential Generator (LCG)
    // Using constants from MMIX by Donald Knuth
    let mut next_octet = || {
        state = state.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
        // High-order bits have the best randomness. Octets stay in 1-255, like in the JS worker.
        (((state >> 32) & 0xFF) as u8).max(1)
    };

    format!(
        "{}.{}.{}.{}",
        next_octet(),
        next_octet(),
        next_octet(),
        next_octet()
    )
}

/// Compares in constant time, so response timing doesn't reveal how much of the key matched.
fn is_valid_key(provided: &str, expected: &str) -> bool {
    if expected.is_empty() || provided.len() != expected.len() {
        return false;
    }
    let difference = provided
        .bytes()
        .zip(expected.bytes())
        .fold(0u8, |accumulated, (a, b)| accumulated | (a ^ b));
    difference == 0
}

fn get_raw_target(request_url: &Url, target_header: Option<String>) -> Option<String> {
    let from_query = request_url
        .query_pairs()
        .find(|(name, value)| name == "url" && !value.is_empty())
        .map(|(_, value)| value.into_owned());

    from_query.or(target_header.filter(|value| !value.is_empty())).or_else(|| {
        let from_path = request_url.path().trim_start_matches('/');
        let is_target = from_path.starts_with("http://") || from_path.starts_with("https://");
        is_target.then(|| from_path.to_string())
    })
}

fn build_target_url(request_url: &Url, raw_target: &str) -> Option<Url> {
    let mut target_url = Url::parse(raw_target).ok()?;
    if !matches!(target_url.scheme(), "http" | "https") {
        return None;
    }

    let extra_params: Vec<(String, String)> = request_url
        .query_pairs()
        .filter(|(name, _)| !ROUTING_PARAMS.contains(&name.as_ref()))
        .map(|(name, value)| (name.into_owned(), value.into_owned()))
        .collect();

    // Touching query_pairs_mut would re-serialize the target's own query, so only do it when needed
    if !extra_params.is_empty() {
        target_url.query_pairs_mut().extend_pairs(&extra_params);
    }
    Some(target_url)
}

fn is_forwardable_header(name: &str) -> bool {
    let lower_name = name.to_lowercase();
    !BLOCKED_REQUEST_HEADERS.contains(&lower_name.as_str()) && !lower_name.starts_with("cf-")
}

fn set_cors_headers(headers: &Headers) -> Result<()> {
    headers.set("Access-Control-Allow-Origin", "*")?;
    headers.set("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS, PATCH, HEAD")?;
    headers.set("Access-Control-Allow-Headers", "*")?;
    Ok(())
}

fn error_response(message: &str, status: u16) -> Result<Response> {
    let response = Response::from_json(&serde_json::json!({ "error": message }))?.with_status(status);
    response.headers().set(ERROR_HEADER, "true")?;
    set_cors_headers(response.headers())?;
    Ok(response)
}

fn build_proxy_request(req: &Request, target_url: &Url) -> Result<Request> {
    let headers = Headers::new();
    for (name, value) in req.headers() {
        if is_forwardable_header(&name) {
            headers.append(&name, &value)?;
        }
    }

    let forwarded_for = match req.headers().get("X-My-X-Forwarded-For")? {
        Some(value) => value,
        None => generate_random_ip(Date::now().as_millis()),
    };
    headers.set("X-Forwarded-For", &forwarded_for)?;

    let method = req.method();
    let mut init = RequestInit::new();
    init.with_method(method.clone());
    init.with_headers(headers);

    if method != Method::Get && method != Method::Head {
        if let Some(body_stream) = req.inner().body() {
            init.with_body(Some(body_stream.into()));
        }
    }

    Request::new_with_init(target_url.as_str(), &init)
}

fn build_proxy_response(mut response: Response, method: &Method) -> Result<Response> {
    let headers = Headers::new();
    for (name, value) in response.headers() {
        // append, not set: a response can carry several Set-Cookie headers
        if !BLOCKED_RESPONSE_HEADERS.contains(&name.to_lowercase().as_str()) {
            headers.append(&name, &value)?;
        }
    }
    set_cors_headers(&headers)?;

    let status = response.status_code();
    if *method == Method::Head || NULL_BODY_STATUSES.contains(&status) {
        return Ok(Response::empty()?.with_status(status).with_headers(headers));
    }

    let body = response.stream()?;
    Ok(Response::from_stream(body)?.with_status(status).with_headers(headers))
}

async fn handle_request(req: Request, env: Env) -> Result<Response> {
    if req.method() == Method::Options {
        let headers = Headers::new();
        set_cors_headers(&headers)?;
        return Ok(Response::empty()?.with_status(204).with_headers(headers));
    }

    let expected_key = env.secret(KEY_BINDING).map(|secret| secret.to_string()).unwrap_or_default();
    let provided_key = req.headers().get(KEY_HEADER)?.unwrap_or_default();
    if !is_valid_key(&provided_key, &expected_key) {
        return error_response("Unauthorized", 401);
    }

    let request_url = req.url()?;
    let Some(raw_target) = get_raw_target(&request_url, req.headers().get("X-Target-URL")?) else {
        return error_response("No target URL specified", 400);
    };
    let Some(target_url) = build_target_url(&request_url, &raw_target) else {
        return error_response("Invalid target URL", 400);
    };

    let response = Fetch::Request(build_proxy_request(&req, &target_url)?).send().await?;
    build_proxy_response(response, &req.method())
}

#[event(fetch)]
pub async fn main(req: Request, env: Env, _ctx: worker::Context) -> Result<Response> {
    utils::set_panic_hook();

    match handle_request(req, env).await {
        Ok(response) => Ok(response),
        Err(error) => {
            console_error!("Proxy request failed: {error:?}");
            error_response("Proxy request failed", 502)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn url(value: &str) -> Url {
        Url::parse(value).unwrap()
    }

    #[test]
    fn test_generate_random_ip_format() {
        let ip = generate_random_ip(1_771_765_050_000);
        let parts: Vec<&str> = ip.split('.').collect();
        assert_eq!(parts.len(), 4, "IP must have 4 octets: {ip}");

        for part in &parts {
            part.parse::<u8>().unwrap_or_else(|_| {
                panic!("Octet '{part}' is not a valid u8 in IP: {ip}")
            });
        }
    }

    #[test]
    fn test_generate_random_ip_nonzero_octets() {
        // With 256 possible values per octet, this many seeds would hit a zero without the guard
        for seed in 0..10_000 {
            let ip = generate_random_ip(seed);
            for part in ip.split('.') {
                let octet: u8 = part.parse().expect("valid octet");
                assert!(octet >= 1, "0 is not a valid octet for X-Forwarded-For: {ip}");
            }
        }
    }

    #[test]
    fn test_generate_random_ip_depends_on_seed() {
        assert_ne!(generate_random_ip(1), generate_random_ip(2));
    }

    #[test]
    fn test_is_valid_key() {
        assert!(is_valid_key("secret", "secret"));
        assert!(!is_valid_key("secreT", "secret"));
        assert!(!is_valid_key("secret2", "secret"));
        assert!(!is_valid_key("", "secret"));
        assert!(!is_valid_key("", ""));
    }

    #[test]
    fn test_target_priority_is_query_then_header_then_path() {
        let request_url = url("https://w.dev/https://path.dev/?url=https://query.dev/");
        let header = Some("https://header.dev/".to_string());
        assert_eq!(get_raw_target(&request_url, header.clone()).unwrap(), "https://query.dev/");

        let request_url = url("https://w.dev/https://path.dev/");
        assert_eq!(get_raw_target(&request_url, header).unwrap(), "https://header.dev/");
        assert_eq!(get_raw_target(&request_url, None).unwrap(), "https://path.dev/");
    }

    #[test]
    fn test_target_is_absent() {
        assert_eq!(get_raw_target(&url("https://w.dev/"), None), None);
        assert_eq!(get_raw_target(&url("https://w.dev/some/path"), None), None);
    }

    #[test]
    fn test_target_keeps_its_own_query() {
        let request_url = url("https://w.dev/");
        let raw = "https://t.dev/?url=a&_t=b&_cb=c&empty=&s=two%20words";
        assert_eq!(build_target_url(&request_url, raw).unwrap().as_str(), raw);
    }

    #[test]
    fn test_extra_params_are_appended_except_routing_ones() {
        let request_url = url("https://w.dev/?url=ignored&_cb=1&_t=2&x=3");
        let target = build_target_url(&request_url, "https://t.dev/?a=1").unwrap();
        assert_eq!(target.as_str(), "https://t.dev/?a=1&x=3");
    }

    #[test]
    fn test_only_http_targets_are_allowed() {
        let request_url = url("https://w.dev/");
        assert!(build_target_url(&request_url, "ftp://t.dev/").is_none());
        assert!(build_target_url(&request_url, "file:///etc/passwd").is_none());
        assert!(build_target_url(&request_url, "not a url").is_none());
    }

    #[test]
    fn test_forwardable_headers() {
        for blocked in ["Host", "X-Proxyflare-Key", "X-Forwarded-For", "CF-Connecting-IP", "cf-ray"] {
            assert!(!is_forwardable_header(blocked), "{blocked} must not be forwarded");
        }
        for allowed in ["User-Agent", "Authorization", "Cookie", "X-Custom"] {
            assert!(is_forwardable_header(allowed), "{allowed} must be forwarded");
        }
    }
}
