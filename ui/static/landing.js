/** Landing page — benchmark stats, scroll reveal, causal chain animation */

function formatPercent(value) {
  if (value == null || Number.isNaN(value)) return "—";
  const rounded = Math.round(value * 100) / 100;
  return `${rounded % 1 === 0 ? rounded.toFixed(0) : rounded.toFixed(2)}%`;
}

async function loadBenchmarkStats() {
  const statEls = {
    cases: document.querySelector('[data-stat="cases"]'),
    iqs: document.querySelector('[data-stat="iqs"]'),
    recall: document.querySelector('[data-stat="recall"]'),
    divergence: document.querySelector('[data-stat="divergence"]'),
    nofab: document.querySelector('[data-stat="nofab"]'),
  };
  if (!statEls.iqs) return;

  try {
    const response = await fetch("/api/benchmark-overview");
    if (!response.ok) return;
    const data = await response.json();
    statEls.cases.textContent = String(data.case_count);
    statEls.iqs.textContent = formatPercent(data.stage_3_iqs_percent);

    const metrics = Object.fromEntries(data.metrics.map((row) => [row.label, row.value_percent]));
    statEls.recall.textContent = formatPercent(metrics["Evidence recall"]);
    statEls.divergence.textContent = formatPercent(metrics["Divergence accuracy"]);
    statEls.nofab.textContent = formatPercent(metrics["No-fabrication"]);
  } catch {
    /* Keep placeholders if API unavailable */
  }
}

function initScrollReveal() {
  const reveals = document.querySelectorAll(".reveal");
  if (!reveals.length || !("IntersectionObserver" in window)) {
    reveals.forEach((el) => el.classList.add("visible"));
    return;
  }

  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("visible");
          observer.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.1, rootMargin: "0px 0px -32px 0px" },
  );

  reveals.forEach((el) => observer.observe(el));
}

function initCausalChainAnimation() {
  const demo = document.getElementById("causal-demo");
  if (!demo || window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    demo?.querySelectorAll(".lp-causal-node, .lp-causal-arrow").forEach((el) => el.classList.add("is-active"));
    return;
  }

  const steps = [...demo.querySelectorAll(".lp-causal-node, .lp-causal-arrow")];
  let index = 0;

  function activateNext() {
    if (index < steps.length) {
      steps[index].classList.add("is-active");
      index += 1;
    } else {
      index = 0;
      steps.forEach((el) => el.classList.remove("is-active"));
    }
  }

  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          activateNext();
          if (!demo.dataset.interval) {
            demo.dataset.interval = setInterval(activateNext, 900);
          }
        } else if (demo.dataset.interval) {
          clearInterval(Number(demo.dataset.interval));
          delete demo.dataset.interval;
          steps.forEach((el) => el.classList.remove("is-active"));
          index = 0;
        }
      });
    },
    { threshold: 0.4 },
  );

  observer.observe(demo);
}

loadBenchmarkStats();
initScrollReveal();
initCausalChainAnimation();
