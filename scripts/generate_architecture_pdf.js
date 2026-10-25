#!/usr/bin/env node
/**
 * Intent-Swarm-Commander — Architecture Documentation PDF Generator
 * 
 * Compiles all architecture documentation and analysis files in docs/ into a single,
 * publication-grade printable PDF with fully rendered vector Mermaid diagrams,
 * cover page, table of contents, and print-optimized typography.
 */

const fs = require('fs');
const path = require('path');
const { chromium } = require('@playwright/test');
const { marked } = require('marked');

const PROJECT_ROOT = path.resolve(__dirname, '..');
const DOCS_DIR = path.join(PROJECT_ROOT, 'docs');
const OUTPUT_PDF = path.join(DOCS_DIR, 'Intent-Swarm-Commander-Architecture.pdf');

// List of documents to include in order
const DOCUMENTS = [
  {
    chapter: 1,
    title: "System Architecture & Core Pipeline",
    file: path.join(DOCS_DIR, 'system_architecture.md'),
    id: "chap-sys-arch"
  },
  {
    chapter: 2,
    title: "Data Flows & Sequence Diagrams",
    file: path.join(DOCS_DIR, 'data_flows.md'),
    id: "chap-data-flows"
  },
  {
    chapter: 3,
    title: "Deployment Architecture & Infrastructure Guide",
    file: path.join(DOCS_DIR, 'deployment.md'),
    id: "chap-deployment"
  },
  {
    chapter: 4,
    title: "Domain-Driven Design (DDD) & Context Architecture",
    file: path.join(DOCS_DIR, 'domain_driven_design.md'),
    id: "chap-ddd"
  },
  {
    chapter: 5,
    title: "System, Service & Entity Overview",
    file: path.join(DOCS_DIR, 'service_and_entity_overview.md'),
    id: "chap-services-entities"
  },
  {
    chapter: 6,
    title: "Architectural Integration Analysis: Poor-Man's Artemis.IA",
    file: path.join(DOCS_DIR, 'analysis', 'compatibility_with_pma.md'),
    id: "chap-pma-analysis"
  }
];

// Helper: Read and convert image to base64
function getBase64Image(filePath) {
  if (fs.existsSync(filePath)) {
    const ext = path.extname(filePath).slice(1).toLowerCase();
    const mime = ext === 'jpg' || ext === 'jpeg' ? 'image/jpeg' : `image/${ext}`;
    const base64 = fs.readFileSync(filePath).toString('base64');
    return `data:${mime};base64,${base64}`;
  }
  return null;
}

async function generatePdf() {
  console.log("============================================================");
  console.log("Intent-Swarm-Commander: Printable Architecture PDF Generator");
  console.log("============================================================");

  // Load images
  const swarmArchImgPath = path.join(DOCS_DIR, 'images', 'swarm_architecture.jpg');
  const swarmArchBase64 = getBase64Image(swarmArchImgPath);
  const imageMap = {};
  if (swarmArchBase64) {
    imageMap['./images/swarm_architecture.jpg'] = swarmArchBase64;
    imageMap['file:///home/remi/Projects/Intent-Swarm-Commander/docs/images/swarm_architecture.jpg'] = swarmArchBase64;
  }

  const allDiagrams = [];
  const parsedChapters = [];

  for (const doc of DOCUMENTS) {
    console.log(`Processing Chapter ${doc.chapter}: ${doc.title}...`);
    let rawMd = fs.readFileSync(doc.file, 'utf8');

    // Replace image references with base64 data URIs
    for (const [imgRef, base64Uri] of Object.entries(imageMap)) {
      rawMd = rawMd.split(imgRef).join(base64Uri);
    }

    // Configure marked renderer for this chapter
    const renderer = new marked.Renderer();
    let chapterDiagramCount = 0;

    renderer.code = function({ text, lang }) {
      if (lang === 'mermaid') {
        chapterDiagramCount++;
        const diagId = `diagram_c${doc.chapter}_d${chapterDiagramCount}`;
        allDiagrams.push({
          id: diagId,
          code: text,
          chapter: doc.chapter,
          index: chapterDiagramCount,
          docTitle: doc.title
        });

        return `
          <div class="mermaid-container" id="${diagId}_container">
            <div id="${diagId}" class="diagram-render-target"></div>
            <div class="mermaid-caption">Figure ${doc.chapter}.${chapterDiagramCount}: ${doc.title} — Architectural Flow</div>
          </div>
        `;
      }
      return `<pre><code class="language-${lang || 'text'}">${text}</code></pre>`;
    };

    const parsedHtml = marked.parse(rawMd, { renderer, gfm: true });

    parsedChapters.push({
      ...doc,
      html: parsedHtml,
      diagramCount: chapterDiagramCount
    });
  }

  console.log(`Extracted total of ${allDiagrams.length} Mermaid diagrams across all chapters.`);

  // Build the complete HTML document
  const fullHtml = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Intent-Swarm-Commander: System Architecture Specification</title>
  <!-- Mermaid.js for Vector Diagram Rendering -->
  <script type="module">
    import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
    mermaid.initialize({
      startOnLoad: false,
      theme: 'neutral',
      securityLevel: 'loose',
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif',
      fontSize: 11,
      flowchart: {
        useMaxWidth: true,
        htmlLabels: true,
        curve: 'basis'
      },
      sequence: {
        useMaxWidth: true,
        showSequenceNumbers: true,
        actorMargin: 30,
        boxMargin: 8
      },
      er: {
        useMaxWidth: true,
        fontSize: 10
      }
    });
    window.mermaid = mermaid;
  </script>
  <style>
    @page {
      size: A4;
      margin: 16mm 12mm 16mm 12mm;
    }

    * {
      box-sizing: border-box;
      -webkit-print-color-adjust: exact !important;
      print-color-adjust: exact !important;
    }

    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      font-size: 8.8pt;
      line-height: 1.45;
      color: #1e293b;
      background: #ffffff;
      margin: 0;
      padding: 0;
    }

    /* ── Cover Page ── */
    .cover-page {
      height: 98vh;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      page-break-after: always;
      break-after: page;
      padding: 22mm 15mm 15mm 15mm;
      background: linear-gradient(180deg, #f8fafc 0%, #ffffff 100%);
      border: 1px solid #cbd5e1;
      border-radius: 6px;
    }

    .cover-top {
      border-bottom: 3px solid #2563eb;
      padding-bottom: 15px;
    }

    .cover-badge {
      display: inline-block;
      font-size: 8.5pt;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 1.5px;
      color: #2563eb;
      background: #eff6ff;
      border: 1px solid #bfdbfe;
      padding: 4px 10px;
      border-radius: 4px;
      margin-bottom: 12px;
    }

    .cover-title {
      font-size: 26pt;
      font-weight: 800;
      line-height: 1.15;
      color: #0f172a;
      margin: 0 0 10px 0;
      letter-spacing: -0.5px;
    }

    .cover-subtitle {
      font-size: 12.5pt;
      font-weight: 400;
      color: #475569;
      margin: 0;
      line-height: 1.4;
    }

    .cover-middle {
      margin: 20px 0;
    }

    .cover-abstract {
      background: #f8fafc;
      border-left: 4px solid #3b82f6;
      padding: 12px 16px;
      border-radius: 0 6px 6px 0;
      font-size: 9.5pt;
      color: #334155;
      line-height: 1.5;
    }

    .cover-meta-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
      margin-top: 20px;
      background: #ffffff;
      border: 1px solid #e2e8f0;
      border-radius: 6px;
      padding: 12px 16px;
    }

    .cover-meta-item {
      font-size: 8.5pt;
    }

    .cover-meta-label {
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      color: #64748b;
      margin-bottom: 2px;
    }

    .cover-meta-value {
      font-weight: 600;
      color: #0f172a;
      font-size: 9.5pt;
    }

    .cover-bottom {
      border-top: 1px solid #cbd5e1;
      padding-top: 12px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 8pt;
      color: #64748b;
    }

    /* ── Table of Contents ── */
    .toc-page {
      page-break-after: always;
      break-after: page;
      padding: 15mm 10mm;
    }

    .toc-title {
      font-size: 18pt;
      font-weight: 800;
      color: #0f172a;
      border-bottom: 2px solid #2563eb;
      padding-bottom: 8px;
      margin-bottom: 18px;
    }

    .toc-list {
      list-style: none;
      padding: 0;
      margin: 0;
    }

    .toc-item {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      padding: 8px 0;
      border-bottom: 1px dashed #cbd5e1;
      font-size: 9.5pt;
    }

    .toc-item strong {
      color: #1e293b;
    }

    .toc-item span.chap-num {
      color: #2563eb;
      font-weight: 700;
      margin-right: 8px;
    }

    /* ── Chapters ── */
    .chapter {
      page-break-before: always;
      break-before: page;
      margin-top: 5px;
    }

    .chapter-banner {
      background: #0f172a;
      color: #ffffff;
      padding: 10px 16px;
      border-radius: 5px;
      margin-bottom: 16px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .chapter-banner .chap-tag {
      font-size: 7.5pt;
      font-weight: 700;
      letter-spacing: 1px;
      text-transform: uppercase;
      background: #2563eb;
      color: #ffffff;
      padding: 3px 8px;
      border-radius: 3px;
    }

    .chapter-banner .chap-heading {
      font-size: 13pt;
      font-weight: 700;
      margin: 0;
    }

    /* ── Typography & Markdown Elements ── */
    h1 {
      font-size: 15pt;
      font-weight: 800;
      color: #0f172a;
      margin-top: 16pt;
      margin-bottom: 8pt;
      border-bottom: 2px solid #e2e8f0;
      padding-bottom: 4pt;
      page-break-after: avoid;
      break-after: avoid;
    }

    h2 {
      font-size: 12pt;
      font-weight: 700;
      color: #1e293b;
      margin-top: 14pt;
      margin-bottom: 6pt;
      border-bottom: 1px solid #f1f5f9;
      padding-bottom: 2pt;
      page-break-after: avoid;
      break-after: avoid;
    }

    h3 {
      font-size: 10pt;
      font-weight: 700;
      color: #334155;
      margin-top: 10pt;
      margin-bottom: 5pt;
      page-break-after: avoid;
      break-after: avoid;
    }

    h4 {
      font-size: 8.8pt;
      font-weight: 700;
      color: #475569;
      margin-top: 7pt;
      margin-bottom: 3pt;
    }

    p {
      margin: 0 0 7pt 0;
      text-align: justify;
    }

    ul, ol {
      margin: 0 0 8pt 0;
      padding-left: 18px;
    }

    li {
      margin-bottom: 2.5pt;
    }

    hr {
      border: 0;
      border-top: 1px solid #e2e8f0;
      margin: 12pt 0;
    }

    blockquote {
      border-left: 3.5px solid #3b82f6;
      background: #f8fafc;
      margin: 8pt 0;
      padding: 6pt 12pt;
      color: #334155;
      font-style: normal;
      border-radius: 0 4px 4px 0;
      page-break-inside: avoid;
      break-inside: avoid;
    }

    /* ── Tables ── */
    table {
      width: 100%;
      border-collapse: collapse;
      margin: 10pt 0;
      font-size: 7.8pt;
      page-break-inside: avoid;
      break-inside: avoid;
    }

    th {
      background: #f1f5f9;
      color: #0f172a;
      font-weight: 700;
      text-align: left;
      padding: 5px 6px;
      border: 1px solid #cbd5e1;
    }

    td {
      padding: 4px 6px;
      border: 1px solid #e2e8f0;
      vertical-align: top;
    }

    tr:nth-child(even) td {
      background-color: #f8fafc;
    }

    /* ── Code & Pre ── */
    code {
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
      font-size: 7.5pt;
      background: #f1f5f9;
      color: #0f172a;
      padding: 1.5px 3.5px;
      border-radius: 3px;
      border: 1px solid #e2e8f0;
    }

    pre {
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 4px;
      padding: 6pt 8pt;
      font-size: 7pt;
      line-height: 1.38;
      overflow-x: hidden;
      white-space: pre-wrap;
      word-break: break-all;
      page-break-inside: avoid;
      break-inside: avoid;
      margin: 8pt 0;
    }

    pre code {
      background: none;
      padding: 0;
      border: none;
      font-size: inherit;
    }

    /* ── Images ── */
    img {
      max-width: 100%;
      height: auto;
      border-radius: 4px;
      border: 1px solid #e2e8f0;
      margin: 8pt 0;
      display: block;
      page-break-inside: avoid;
      break-inside: avoid;
    }

    /* ── Mermaid Diagrams ── */
    .mermaid-container {
      margin: 12pt auto;
      padding: 8pt;
      background: #ffffff;
      border: 1px solid #cbd5e1;
      border-radius: 5px;
      text-align: center;
      page-break-inside: avoid;
      break-inside: avoid;
      box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    }

    .mermaid-container svg {
      max-width: 100% !important;
      height: auto !important;
      display: block;
      margin: 0 auto;
    }

    .mermaid-caption {
      font-size: 7.5pt;
      font-weight: 600;
      color: #64748b;
      margin-top: 5pt;
      text-align: center;
    }
  </style>
</head>
<body>

  <!-- ── COVER PAGE ── -->
  <div class="cover-page">
    <div class="cover-top">
      <div class="cover-badge">Technical Architecture & Systems Engineering Manual</div>
      <h1 class="cover-title">INTENT-SWARM-COMMANDER</h1>
      <p class="cover-subtitle">Tactical Multi-Drone Swarm Command & Control (C2) Orchestration Platform</p>
    </div>

    <div class="cover-middle">
      <div class="cover-abstract">
        <strong>Executive Summary:</strong> Intent-Swarm-Commander (ISC v0.2.0) translates high-level military intent orders (SMEAC) into synchronized, resilient autonomous multi-drone swarm operations. Designed under EU AI Act and SORA 2.5 safety mandates, the platform incorporates a compliant 7-step pipeline featuring Just-In-Time (JIT) Model Context Protocol (MCP) authentication, Guardian Critic constraint verification solvers, Human-in-the-Loop (HITL) approval gates, Temporal durable workflow orchestration, and edge perception bridges connecting to physical Raspberry Pi 5 companion computers and PX4/Gazebo simulations.
      </div>

      <div class="cover-meta-grid">
        <div class="cover-meta-item">
          <div class="cover-meta-label">System Version</div>
          <div class="cover-meta-value">0.2.0 (Production Release)</div>
        </div>
        <div class="cover-meta-item">
          <div class="cover-meta-label">Security & Compliance</div>
          <div class="cover-meta-value">EU AI Act (HITL) • SORA 2.5 • MCP OAuth 2.1</div>
        </div>
        <div class="cover-meta-item">
          <div class="cover-meta-label">Architecture Framework</div>
          <div class="cover-meta-value">Domain-Driven Design (DDD) • Clean Architecture</div>
        </div>
        <div class="cover-meta-item">
          <div class="cover-meta-label">Document Date</div>
          <div class="cover-meta-value">October 2026</div>
        </div>
      </div>
    </div>

    <div class="cover-bottom">
      <div><strong>Classification:</strong> UNCLASSIFIED / ARCHITECTURAL REVIEW</div>
      <div><strong>Repository:</strong> Intent-Swarm-Commander</div>
    </div>
  </div>

  <!-- ── TABLE OF CONTENTS ── -->
  <div class="toc-page">
    <div class="toc-title">Table of Contents</div>
    <ul class="toc-list">
      ${DOCUMENTS.map(doc => `
        <li class="toc-item">
          <span><span class="chap-num">Chapter ${doc.chapter}.</span> <strong>${doc.title}</strong></span>
          <span style="color: #64748b;">Section ${doc.chapter}.0</span>
        </li>
      `).join('')}
    </ul>
    <div style="margin-top: 30px; padding: 12px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; font-size: 8pt; color: #475569;">
      <strong>Note for Offline Reviewers:</strong> All system architectures, data sequence flows, infrastructure deployments, domain models, and entity diagrams have been statically rendered as high-resolution vector graphics directly within this document. External hyperlinks point to local codebase source files for drill-down inspection.
    </div>
  </div>

  <!-- ── CHAPTERS ── -->
  ${parsedChapters.map(doc => `
    <div class="chapter" id="${doc.id}">
      <div class="chapter-banner">
        <div>
          <span class="chap-tag">Chapter ${doc.chapter}</span>
          <span style="font-size: 12pt; font-weight: 700; margin-left: 8px;">${doc.title}</span>
        </div>
        <div style="font-size: 8pt; color: #94a3b8;">ISC v0.2.0</div>
      </div>
      <div class="markdown-body">
        ${doc.html}
      </div>
    </div>
  `).join('')}

</body>
</html>
  `;

  // Launch Playwright and render PDF
  const browser = await chromium.launch({
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });

  const page = await browser.newPage();

  page.on('console', msg => {
    if (msg.type() === 'error') console.error('BROWSER ERROR:', msg.text());
  });
  page.on('pageerror', err => console.error('PAGE EXCEPTION:', err.message));

  // Set viewport large enough for layout
  await page.setViewportSize({ width: 1200, height: 1600 });

  console.log("Loading HTML into Playwright browser context...");
  await page.setContent(fullHtml, { waitUntil: 'networkidle' });

  console.log("Waiting for Mermaid module to initialize...");
  await page.waitForFunction(() => !!window.mermaid, { timeout: 20000 });

  console.log(`Rendering ${allDiagrams.length} Mermaid diagrams individually...`);
  for (let i = 0; i < allDiagrams.length; i++) {
    const diag = allDiagrams[i];
    const renderResult = await page.evaluate(async (d) => {
      try {
        const renderId = `svg_${d.id}_${Date.now()}`;
        const { svg } = await window.mermaid.render(renderId, d.code);
        const container = document.getElementById(d.id);
        if (container) {
          container.innerHTML = svg;
          const svgEl = container.querySelector('svg');
          if (svgEl) {
            svgEl.style.maxWidth = '100%';
            svgEl.style.height = 'auto';
          }
        }
        return { ok: true };
      } catch (err) {
        return { ok: false, error: err.message || String(err) };
      }
    }, diag);

    if (renderResult.ok) {
      console.log(`  [${i + 1}/${allDiagrams.length}] Rendered diagram ${diag.id} (Chapter ${diag.chapter})`);
    } else {
      console.warn(`  [${i + 1}/${allDiagrams.length}] WARNING: Failed rendering diagram ${diag.id}: ${renderResult.error}`);
    }
  }

  // Allow layout settling
  await page.waitForTimeout(1500);

  console.log(`Compiling print-optimized PDF to: ${OUTPUT_PDF}...`);
  await page.pdf({
    path: OUTPUT_PDF,
    format: 'A4',
    printBackground: true,
    displayHeaderFooter: true,
    margin: {
      top: '18mm',
      bottom: '18mm',
      left: '12mm',
      right: '12mm'
    },
    headerTemplate: `
      <div style="font-size: 7.5pt; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #64748b; width: 100%; border-bottom: 1px solid #e2e8f0; padding-bottom: 3px; display: flex; justify-content: space-between; padding-left: 12mm; padding-right: 12mm;">
        <span><strong>Intent-Swarm-Commander (v0.2.0)</strong> — Technical Reference Architecture</span>
        <span style="font-weight: 700; color: #3b82f6;">UNCLASSIFIED</span>
      </div>
    `,
    footerTemplate: `
      <div style="font-size: 7.5pt; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #64748b; width: 100%; border-top: 1px solid #e2e8f0; padding-top: 3px; display: flex; justify-content: space-between; padding-left: 12mm; padding-right: 12mm;">
        <span>Tactical Multi-Drone C2 Architecture Manual • October 2026</span>
        <span>Page <span class="pageNumber"></span> of <span class="totalPages"></span></span>
      </div>
    `
  });

  await browser.close();

  const stats = fs.statSync(OUTPUT_PDF);
  console.log(`\n============================================================`);
  console.log(`PRINTABLE PDF GENERATION COMPLETE!`);
  console.log(`File: ${OUTPUT_PDF}`);
  console.log(`Size: ${(stats.size / 1024 / 1024).toFixed(2)} MB (${stats.size} bytes)`);
  console.log(`============================================================\n`);
}

generatePdf().catch(err => {
  console.error("FATAL: Failed to generate architecture PDF:", err);
  process.exit(1);
});
