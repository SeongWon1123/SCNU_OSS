# api image: python 3.12-slim + git + semgrep(pinned) + gitleaks(versioned release, sha256-verified)
# + vendored p/ci ruleset. Runtime network dependency for scanning: 0 (SPEC.md:200).
# The pin's validity (gitleaks version, semgrep version, p-ci fetch) is proven by the
# image build in todo 4 (`docker compose build api`).
FROM python:3.12-slim

# Versioned release asset only — releases/latest/download 404s on versioned asset
# names, and the arch is x64 (not amd64) in gitleaks release naming.
ARG GITLEAKS_VERSION

RUN apt-get update \
 && apt-get install -y --no-install-recommends git curl ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && pip install --no-cache-dir semgrep==1.176.0

# gitleaks: download the versioned tarball and verify its sha256 against the
# release's official checksums.txt (per-asset .sha256 companions are not published;
# verified 404 for v8.30.1 — see task-3 evidence).
RUN test -n "${GITLEAKS_VERSION}" \
 && ASSET="gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz" \
 && curl -fsSL -o /tmp/gitleaks.tar.gz \
      "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/${ASSET}" \
 && curl -fsSL -o /tmp/gitleaks.checksums \
      "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_checksums.txt" \
 && EXPECTED=$(grep " ${ASSET}\$" /tmp/gitleaks.checksums | awk '{print $1}') \
 && test -n "${EXPECTED}" \
 && echo "${EXPECTED}  /tmp/gitleaks.tar.gz" | sha256sum -c - \
 && tar -xzf /tmp/gitleaks.tar.gz -C /usr/local/bin gitleaks \
 && chmod 0755 /usr/local/bin/gitleaks \
 && rm -f /tmp/gitleaks.tar.gz /tmp/gitleaks.checksums

# Vendor the p/ci ruleset at build time. If the URL returns invalid YAML (e.g. an
# HTML error page), semgrep --validate fails and the build falls back to kr-only
# rules per SPEC.md:212 (Gate 1), recording the fact in the image.
RUN mkdir -p /app/rules/vendor \
 && if curl -fsSL https://semgrep.dev/c/p/ci -o /app/rules/vendor/p-ci.yaml \
      && semgrep --validate --config /app/rules/vendor/p-ci.yaml > /dev/null 2>&1; then \
      sha256sum /app/rules/vendor/p-ci.yaml | awk '{print $1}' > /app/rules/vendor/p-ci.sha256; \
    else \
      rm -f /app/rules/vendor/p-ci.yaml /app/rules/vendor/p-ci.sha256; \
      echo "p-ci fetch/validate failed -> kr-only fallback (SPEC.md:212)" > /app/rules/vendor/p-ci.FALLBACK; \
    fi

# uid 10001: the unprivileged identity the worker runs as (compose pins user 10001:10001).
RUN useradd --uid 10001 --user-group --no-create-home --shell /usr/sbin/nologin scanner

WORKDIR /app
