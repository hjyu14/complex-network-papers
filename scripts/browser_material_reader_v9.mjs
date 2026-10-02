// Invoke only from cua_repl with its documented, authorised tab handles.
// This module performs DOM reads and normal navigation, never network requests,
// session-cookie export, CAPTCHA solving, PDF downloads or access bypass.
export async function readMetadata(tab, doi) {
  return await tab.playwright.evaluate((doi) => {
    const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();
    const meta = {};
    for (const n of document.querySelectorAll('meta[name],meta[property]')) {
      const k = (n.getAttribute('name') || n.getAttribute('property') || '').toLowerCase();
      meta[k] = n.getAttribute('content') || '';
    }
    const visible = document.body.innerText;
    const title = meta.citation_title || norm(document.querySelector('h1.heading-lg-bold')?.textContent) || norm(document.querySelector('h1')?.textContent);
    const identity = (meta.citation_doi || meta['dc.identifier'] || '').toLowerCase();
    const textDois = [...visible.matchAll(/DOI:\s*(?:https?:\/\/doi\.org\/)?(10\.\d{4,9}\/[^\s<>]+)/gi)].map(m=>m[1].toLowerCase());
    const metadataMatch = identity.replace(/^https?:\/\/doi.org\//,'').replace(/^doi:/,'').trim() === doi.toLowerCase();
    const directDoiLink = [...document.querySelectorAll('a[href]')].some(a => (a.getAttribute('href') || '').toLowerCase() === 'https://doi.org/' + doi.toLowerCase());
    // Science Careers pages may have a separate web DOI and link their
    // journal version via the labelled PDF link. Read only its href.
    const journalVersionLink = location.hostname.endsWith('science.org') ? [...document.querySelectorAll('a[href]')].find(a=>norm(a.textContent)==='Download PDF' && a.href.toLowerCase().split('?')[0].endsWith('/doi/epdf/'+doi.toLowerCase())) : null;
    const doiMatch = metadataMatch || textDois.includes(doi.toLowerCase()) || directDoiLink || Boolean(journalVersionLink);
    const labelledHeadings = [...document.querySelectorAll('h2,h3,h4')].filter(n => norm(n.textContent).toLowerCase() === 'abstract');
    let abstract = meta.citation_abstract || '';
    let abstractBasis = abstract ? 'citation_abstract' : null;
    if (!abstract) {
      for (const heading of labelledHeadings) {
        let n = heading.parentElement;
        if (n && norm(n.innerText).length > 80 && norm(n.innerText).length < 14000) {
          abstract = norm(n.innerText).replace(/^Abstract\s*/i, '');
          abstractBasis = 'DOM section with Abstract heading';
          break;
        }
      }
    }
    const acceptedPaper = document.title.includes('Accepted Paper') || (location.pathname.includes('/accepted/') && /Accepted Paper/.test(visible));
    const pub = visible.match(/Published\s+(\d{1,2}\s+[A-Za-z]+,?\s+\d{4})/);
    const accepted = visible.match(/Accepted\s+(\d{1,2}\s+[A-Za-z]+,?\s+\d{4})/);
    const available = doiMatch && abstract.split(/\s+/).filter(Boolean).length >= 10;
    const headings = [...document.querySelectorAll('h1,h2,h3,h4')].map(n=>norm(n.textContent));
    const aipDateline = location.hostname === 'pubs.aip.org' ? norm(document.querySelector('.article-groups.left-flag')?.textContent) : '';
    const scienceTypeNode = location.hostname.endsWith('science.org') ? document.querySelector('.meta-panel__type') || document.querySelector('.news-article__hero__top-meta') : null;
    const visibleType = location.hostname.endsWith('pnas.org') ? norm(document.querySelector('article header .meta-panel__type')?.textContent || document.querySelector('.meta-panel__type')?.textContent) : scienceTypeNode ? norm(scienceTypeNode.textContent) : aipDateline ? aipDateline.split('|')[0].trim() : '';
    const abstractSections = labelledHeadings.map(n=>norm(n.parentElement?.innerText).replace(/^Abstract\s*/i,'')).filter(Boolean);
    const emptyAbstract = labelledHeadings.length > 0 && abstractSections.length === 0 && !abstract;
    const barrier = /Are you a robot|Verify you are human|Verifying you are human|Just a moment|Access denied|Checking your browser|There was a problem providing the content you requested|安全验证|验证成功.*等待|请验证您是真人|请确认您是真人/i.test(document.title + ' ' + visible.slice(0,1200));
    return {
      doi, source_url:location.href, retrieved_at:new Date().toISOString(), title,
      doi_match:doiMatch, article_type:meta.citation_article_type || meta['dc.type'] || null,
      doi_identity_basis:metadataMatch ? 'citation_doi_or_dc_identifier' : directDoiLink ? 'direct_doi_link' : textDois.includes(doi.toLowerCase()) ? 'visible_DOI_label' : journalVersionLink ? 'labelled_link_to_journal_version' : null,
      journal_version_link:journalVersionLink?.href || null,
      associated_web_doi:journalVersionLink ? meta.publication_doi || null : null,
      visible_article_type:visibleType || null,
      visible_article_type_basis:visibleType ? (location.hostname.endsWith('pnas.org') ? 'article header .meta-panel__type' : aipDateline ? '.article-groups.left-flag' : scienceTypeNode?.classList.contains('meta-panel__type') ? '.meta-panel__type' : '.news-article__hero__top-meta') : null,
      publisher_header_dateline:aipDateline || null,
      abstract_section_empty:emptyAbstract,
      abstract_section_heading_present:labelledHeadings.length > 0,
      journal:meta.citation_journal_title || null, issn:meta.citation_issn || null,
      online_date:meta.citation_online_date || (doi.startsWith('10.1103/') && !acceptedPaper ? (pub?.[1] || meta.citation_date) : null) || null,
      publication_date:meta.citation_publication_date || null,
      accepted_date:accepted?.[1] || null,
      publisher_status:acceptedPaper ? 'accepted_paper' : (pub || meta.citation_online_date ? 'published' : 'unverified'),
      abstract_available:available, abstract_word_count:available ? abstract.split(/\s+/).length : 0,
      abstract_basis:abstractBasis, abstract_not_archived:true,
      date_evidence:['citation_online_date','citation_publication_date','citation_date'].filter(k=>meta[k]).map(k=>({label:k,value:meta[k],url:location.href})),
      scope_terms: available ? [...new Set(abstract.match(/\b(?:networks?|graphs?|hypergraphs?|synchroni\w+|percolation|communities|centralit\w+|epidemic\w+|topolog\w+|coupl\w+|spreading|connectiv\w+)\b/gi) || [])].sort() : [],
      access_gate:barrier ? 'verification_or_access_barrier' : /Access the full article|CHECK ACCESS/i.test(visible) ? 'full_article_access_gate' : null,
      status:barrier ? 'blocked' : doiMatch ? 'identity_confirmed' : 'identity_unconfirmed',
      headings:headings.slice(0,16), classification_deferred:true
    };
  }, doi);
}

const lastNavigationAt = new Map();

export async function runBatch({tab, rows, fs, out, existing, batchSize=10, minNavigationIntervalMs=0}) {
  const results = existing || [];
  const initialCount = results.length;
  const done = new Set(results.map(r=>r.doi));
  const todo = rows.filter(r=>!done.has(r.doi)).slice(0,batchSize);
  for (const row of todo) {
    let result;
    try {
      // Pace ordinary navigation between completed page reads. This does
      // not change authentication, browser identity or access controls.
      const pause = Math.max(0, minNavigationIntervalMs - (Date.now() - (lastNavigationAt.get(tab.id) || 0)));
      if (pause) await new Promise(resolve=>setTimeout(resolve,pause));
      lastNavigationAt.set(tab.id,Date.now());
      await tab.goto(row.publisher_url);
      await tab.getAXState({emit:false});
      result = await readMetadata(tab, row.doi);
      if (!result.doi_match && result.status !== 'blocked' && !row.doi.startsWith('10.1103/')) {
        try {
          await tab.playwright.locator('meta[name="citation_doi"]').waitFor({state:'attached',timeoutMs:10000});
          await tab.getAXState({emit:false});
          result = await readMetadata(tab,row.doi);
        } catch { /* preserve unresolved page rather than invent fields */ }
      }
      // This is a batch access audit; a blocked entry is recorded and skipped.
      // No click, login, CAPTCHA response, cookie or token is extracted.
    } catch (error) {
      const navigationError = String(error.message || error).slice(0,140);
      result = {doi:row.doi,source_url:row.publisher_url,status:'navigation_error',abstract_available:false,error:navigationError};
      // A navigation observation timeout does not prove the page failed to
      // load. Inspect the same tab before recording a material failure.
      try {
        await tab.getAXState({emit:false});
        const loaded = await readMetadata(tab,row.doi);
        if (loaded.doi_match || loaded.status === 'blocked') {
          result = {...loaded,navigation_warning:navigationError};
        }
      } catch { /* retain the verified execution error; no repeated navigation */ }
    }
    results.push(result);
    const payload = {complete:false,counts:{processed:results.length,abstract_found:results.filter(r=>r.abstract_available).length,blocked:results.filter(r=>r.status==='blocked').length},results};
    await fs.writeFile(out+'.tmp',JSON.stringify(payload,null,2)+'\n','utf8');
    for (let attempt=0; ; attempt++) {
      try {
        await fs.rename(out+'.tmp',out);
        break;
      } catch (error) {
        // Windows readers can briefly hold the previous checkpoint open.
        // Retry only the save; never repeat the article navigation.
        if (!['EPERM','EACCES'].includes(error.code) || attempt >= 2) throw error;
        await new Promise(resolve=>setTimeout(resolve,200*(attempt+1)));
      }
    }
    if(result.status === 'blocked') break;
  }
  return {processed:results.length,batch_processed:results.length-initialCount,abstract_found:results.filter(r=>r.abstract_available).length,blocked:results.filter(r=>r.status==='blocked').length};
}
