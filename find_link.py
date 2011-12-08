# coding=utf-8
from flask import Flask, render_template, request, Markup, redirect, url_for
from time import time
from datetime import datetime
import urllib, json, re, os, sys

app = Flask(__name__)
last_slash = __file__.rfind('/')
key = open(__file__[:last_slash+1] + 'key').read()
if key[-1] == '\n':
    key = key[:-1]
Flask.secret_key = key
query_url = 'http://en.wikipedia.org/w/api.php?format=json&action=query&'
#srprop = 'size|wordcount|timestamp|score|snippet|titlesnippet|sectionsnippet|sectiontitle|redirectsnippet|redirecttitle|hasrelated'
search_params = 'list=search&srwhat=text&srlimit=50&srsearch='
new_page_params = 'list=recentchanges&rclimit=50&rctype=new&rcnamespace=0&rcshow=!redirect'
backlink_params = 'list=backlinks&bllimit=500&blnamespace=0&bltitle='
redirect_params = 'list=backlinks&blfilterredir=redirects&bllimit=500&blnamespace=0&bltitle='
content_params = 'prop=revisions&rvprop=content|timestamp&titles='
link_params = 'prop=links&pllimit=500&plnamespace=0&titles='
templates_params = 'prop=templates&tllimit=500&tlnamespace=10&titles='
allpages_params = 'list=allpages&apnamespace=0&apfilterredir=nonredirects&aplimit=500&apprefix='
info_params = 'action=query&prop=info&redirects&titles='
categorymembers_params = 'action=query&list=categorymembers&cmnamespace=0&cmlimit=500&cmtitle='
cat_start_params = 'list=allpages&apnamespace=14&apfilterredir=nonredirects&aplimit=500&apprefix='

save_to_cache = False

def commify(amount):
    amount = str(amount)
    firstcomma = len(amount)%3 or 3  # set to 3 if would make a leading comma
    first, rest = amount[:firstcomma], amount[firstcomma:]
    segments = [first] + [rest[i:i+3] for i in range(0, len(rest), 3)]
    return ",".join(segments)

def test_commify():
    assert commify(1) == '1'
    assert commify(2222) == '2,222'
    assert commify('3333') == '3,333'

re_space_or_dash = re.compile('[ -]')

def is_title_case(phrase):
    return all(term[0].isupper() and term[1:].islower() for term in re_space_or_dash.split(phrase))

def test_is_title_case():
    assert is_title_case('Test')
    assert is_title_case('Test Test')
    assert not is_title_case('test')
    assert not is_title_case('TEST TEST')
    assert not is_title_case('test test')
    assert not is_title_case('tEst Test')

class AppURLopener(urllib.FancyURLopener):
    version = "find-link/2.0 (contact: edwardbetts@gmail.com)"

urllib._urlopener = AppURLopener()

def urlquote(s):
    return urllib.quote_plus(s.encode('utf-8'))

def test_urlquote():
    assert urlquote('test') == 'test'
    assert urlquote('test test') == 'test+test'
    assert urlquote(u'na\xefve') == 'na%C3%AFve'

def web_get(params):
    data = urllib.urlopen(query_url + params).read()
    if save_to_cache:
        out = open('cache/' + str(time()), 'w')
        print >> out, params
        print >> out, data
        out.close()
    return json.loads(data)

def wiki_search(q):
    search_url = search_params + urlquote('"%s"' % q)
    ret = web_get(search_url)
    totalhits = ret['query']['searchinfo']['totalhits']
    results = ret['query']['search']
    for i in range(3):
        if 'query-continue' not in ret:
            break
        sroffset = ret['query-continue']['search']['sroffset']
        ret = web_get(search_url + ('&sroffset=%d' % sroffset))
        results += ret['query']['search']
    return (totalhits, results)

class Missing (Exception):
    pass

def get_wiki_info(q):
    ret = web_get(info_params + urlquote(q))
    redirects = []
    if ret['query'].get('redirects'):
        redirects = ret['query']['redirects']
        assert len(redirects) == 1
    if 'missing' in ret['query']['pages'].values()[0]:
        raise Missing
    return redirects[0]['to'] if redirects else None

def test_get_wiki_info():
    global web_get
    web_get = lambda(param): {
        "query":{
            "normalized":[{
                "from":"government budget deficit",
                "to":"Government budget deficit"
            }],
            "pages":{
                "312605":{
                    "pageid":312605,"ns":0,"title":"Government budget deficit","touched":"2011-11-24T22:06:21Z","lastrevid":462258859,"counter":"","length":14071
                }
            }
        }
    }

    redirects = get_wiki_info('government budget deficit')
    assert redirects == None

    web_get = lambda(param): {
        "query":{
            "normalized":[{"from":"government budget deficits","to":"Government budget deficits"}],
            "pages":{"-1":{"ns":0,"title":"Government budget deficits","missing":""}}
        }
    }
    is_missing = False
    try:
        redirects = get_wiki_info('government budget deficits')
    except Missing:
        is_missing = True
    assert is_missing

def cat_start(q):
    ret = web_get(cat_start_params + urlquote(q))
    return [doc['title'] for doc in ret['query']['allpages'] if doc['title'] != q]

def test_cat_start():
    global web_get
    web_get = lambda params: {"query":{"allpages":[]}}
    assert cat_start('test123') == []

def all_pages(q):
    ret = web_get(allpages_params + urlquote(q))
    return [doc['title'] for doc in ret['query']['allpages'] if doc['title'] != q]

def test_all_pages():
    global web_get
    web_get = lambda params: {"query":{"allpages":[{"pageid":312605,"ns":0,"title":"Government budget deficit"}]}}
    assert all_pages('Government budget deficit') == []

def categorymembers(q):
    ret = web_get(categorymembers_params + urlquote(q[0].upper()) + urlquote(q[1:]))
    return [doc['title'] for doc in ret['query']['categorymembers'] if doc['title'] != q]

def test_categorymembers():
    global web_get
    web_get = lambda params: {"query":{"categorymembers":[]}}
    assert categorymembers('test123') == []

def page_links(titles):
    titles = list(titles)
    assert titles
    ret = web_get(link_params + urlquote('|'.join(titles)))
    return dict((doc['title'], set(l['title'] for l in doc['links'])) for doc in ret['query']['pages'].itervalues() if 'links' in doc)

def is_disambig(doc):
    return any('disambig' in t or t.endswith('dis') or t == 'template:surname' for t in (t['title'].lower() for t in doc.get('templates', [])))

def test_is_disambig():
    assert not is_disambig({})
    assert is_disambig({ 'templates': [ {'title': 'disambig'}, {'title': 'magic'}] })
    assert is_disambig({ 'templates': [ {'title': 'geodis'}] })
    assert is_disambig({ 'templates': [ {'title': 'Disambig'}] })

def find_disambig(titles):
    titles = list(titles)
    assert titles
    pos = 0
    disambig = []
    while pos < len(titles):
        ret = web_get(templates_params + urlquote('|'.join(titles[pos:pos+50])))
        disambig.extend(doc['title'] for doc in ret['query']['pages'].itervalues() if is_disambig(doc))
        for i in range(3):
            if 'query-continue' not in ret:
                break
            tlcontinue = ret['query-continue']['templates']['tlcontinue']
            ret = web_get(templates_params + urlquote('|'.join(titles[pos:pos+50])) + '&tlcontinue=' + urlquote(tlcontinue))
            disambig.extend(doc['title'] for doc in ret['query']['pages'].itervalues() if is_disambig(doc))
        pos += 50

    return disambig

re_non_letter = re.compile('\W', re.U)
def norm(s):
    s = re_non_letter.sub('', s).lower()
    return s[:-1] if s and s[-1] == 's' else s

def test_norm():
    assert norm('X') == 'x'
    assert norm('Tables') == 'table'
    assert norm('Tables!!!') == 'table'

def wiki_redirects(q): # pages that link here
    docs = web_get(redirect_params + urlquote(q))['query']['backlinks']
    assert all('redirect' in doc for doc in docs)
    return (doc['title'] for doc in docs)

def wiki_backlink(q):
    ret = web_get(backlink_params + urlquote(q))
    docs = ret['query']['backlinks']
    while 'query-continue' in ret:
        blcontinue = ret['query-continue']['backlinks']['blcontinue']
        ret = web_get(backlink_params + urlquote(q) + '&blcontinue=' + urlquote(blcontinue))
        docs += ret['query']['backlinks']

    articles = set(doc['title'] for doc in docs if 'redirect' not in doc)
    redirects = set(doc['title'] for doc in docs if 'redirect' in doc)
    return (articles, redirects)

def test_en_dash():
    title = u'obsessive\u2013compulsive disorder'
    content = 'This is a obsessive-compulsive disorder test'
    (c, r) = find_link_in_content(title, content)
    assert r == title
    assert c == u'This is a [[obsessive\u2013compulsive disorder]] test'

    content = 'This is a [[obsessive-compulsive]] disorder test'
    (c, r) = find_link_in_content(title, content)
    assert r == title
    assert c == u'This is a [[obsessive\u2013compulsive disorder]] test'

def test_avoid_link_in_heading():
    tp = 'test phrase'
    content = '''
=== Test phrase ===

This sentence contains the test phrase.'''

    (c, r) = find_link_in_content(tp, content)
    assert c == content.replace(tp, '[[' + tp + ']]')
    assert r == tp

re_cite = re.compile('<ref>\s*{{cite.*}}\s*</ref>', re.I | re.S)
def parse_cite(text):
    prev = 0
    for m in re_cite.finditer(text):
        yield ('text', text[prev:m.start()])
        yield ('cite', m.group(0))
        prev = m.end()
    yield ('text', text[prev:])

def test_avoid_link_in_cite():
    tp = 'magic'
    content = 'test <ref>{{cite web|title=Magic|url=http://magic.com}}</ref>'
    (c, r) = find_link_in_content(tp, content + ' ' + tp)
    assert c == content + ' [[' + tp + ']]' 
    assert r == tp

    import py.test
    with py.test.raises(NoMatch):
        find_link_in_content(tp, content)

    tp = 'abc'
    content = '==Early life==\n<ref>{{cite news|}}</ref>abc'
    (c, r) = find_link_in_content(tp, content)
    assert c == content.replace(tp, '[[' + tp + ']]')
    assert r == tp

def test_find_link_in_content():
    get_case_from_content = lambda s: None
    import py.test
    with py.test.raises(NoMatch):
        find_link_in_content('foo', 'bar')

    with py.test.raises(NoMatch):
        input_content = 'Able to find this test\n\nphrase in an article.'
        find_link_in_content('test phrase', input_content)

    with py.test.raises(NoMatch):
        input_content = 'Able to find this test  \n  \n  phrase in an article.'
        find_link_in_content('test phrase', input_content)

    otrain = 'Ticketing on the O-Train works entirely on a proof-of-payment basis; there are no ticket barriers or turnstiles, and the driver does not check fares.'
    (c, r) = find_link_in_content('ticket barriers', otrain, linkto='turnstile')
    assert c == otrain.replace('turnstile', '[[turnstile]]')
    assert r == 'turnstile'

    content = [
        'Able to find this test phrase in an article.',
        'Able to find this test  phrase in an article.',
        'Able to find this test\n  phrase in an article.',
        'Able to find this test  \nphrase in an article.',
        'Able to find this test\nphrase in an article.',
        'Able to find this test-phrase in an article.', 
        'Able to find this test PHRASE in an article.', 
        'Able to find this TEST PHRASE in an article.', 
        'Able to find this test\nPhrase in an article.', 
        'Able to find this [[test]] phrase in an article.',
        'Able to find this TEST [[PHRASE]] in an article.', 
        'Able to find this testphrase in an article.']

    for input_content in content:
        (c, r) = find_link_in_content('test phrase', input_content)
        assert c == 'Able to find this [[test phrase]] in an article.'
        assert r == 'test phrase'

    global web_get
    title = 'London congestion charge'
    web_get = lambda params: {
        'query': { 'pages': { 1: { 'revisions': [{
            '*': "'''" + title + "'''"
            }]}}
    }}

    article = 'MyCar is exempt from the London Congestion Charge, road tax and parking charges.'
    (c, r) = find_link_in_content('London congestion charge', article)
    assert r == 'London congestion charge'

class NoMatch(Exception):
    pass

re_heading = re.compile(r'^\s*(=+)\s*(.+)\s*\1\s*$')
def section_iter(text):
    cur_section = ''
    heading = None
    for line in text.splitlines(True):
        m = re_heading.match(line)
        if not m:
            cur_section += line
            continue
        if cur_section or heading:
            yield (heading, cur_section)
        heading = m.group()
        cur_section = ''
        continue
    yield (heading, cur_section)

def test_section_iter():
    assert list(section_iter('test')) == [(None, 'test')]
    text = '''==Heading==
Paragraph'''
    text = '''==Heading 1 ==
Paragraph 1.
==Heading 2 ==
Paragraph 2.
'''
    assert list(section_iter(text)) == [('==Heading 1 ==\n', 'Paragraph 1.\n'), ('==Heading 2 ==\n', 'Paragraph 2.\n')]

en_dash = u'\u2013'
trans = { ',': ',?', ' ': ' *[-\n]? *' }
trans[en_dash] = trans[' ']

trans2 = { ' ': r"('?s?\]\])?'?s? ?(\[\[)?" }
trans2[en_dash] = trans2[' ']

patterns = [
    lambda q: re.compile('(%s)%s' % (q[0], q[1:]), re.I),
    lambda q: re.compile('(%s)%s' % (q[0], ''.join(trans.get(c, c) for c in q[1:])), re.I),
    lambda q: re.compile(r'(?:\[\[)?(%s)%s(?:\]\])?' % (q[0], ''.join('-?' + trans2.get(c, c) for c in q[1:])), re.I),
]

def test_patterns():
    q = 'San Francisco'
    assert patterns[0](q).pattern == '(S)' + q[1:]
    assert patterns[1](q).pattern == '(S)an *[-\n]? *' + q[4:]

def match_found(m, q, linkto):
    if q[1:] == m.group(0)[1:]:
        replacement = m.group(1) + q[1:]
    elif any(c.isupper() for c in q[1:]) or m.group(0) == m.group(0).upper():
        replacement = q
    elif is_title_case(m.group(0)):
        replacement = get_case_from_content(q)
        if replacement is None:
            replacement = q.lower()
    else:
        replacement = m.group(1) + q[1:]
    assert replacement
    if linkto:
        if linkto[0].isupper() and replacement[0] == linkto[0].lower():
            linkto = linkto[0].lower() + linkto[1:]
        replacement = linkto + '|' + replacement
    return replacement

def find_link_in_content(q, content, linkto=None):
    if linkto:
        try:
            return find_link_in_content(linkto, content)
        except NoMatch:
            pass
    re_link = re.compile('([%s%s])%s' % (q[0].lower(), q[0].upper(), q[1:]))
    sections = list(section_iter(content))
    replacement = None
    for pattern in patterns:
        re_link = pattern(q)
        new_content = ''
        for header, section_text in sections:
            if header:
                new_content += header 
            for token_type, text in parse_cite(section_text):
                if token_type == 'text' and not replacement:
                    m = re_link.search(text)
                    if m:
                        replacement = match_found(m, q, linkto)
                        text = re_link.sub(lambda m: "[[%s]]" % replacement, text, count=1)
                new_content += text
        if replacement:
            return (new_content, replacement)
    raise NoMatch

def test_get_case_from_content(): # test is broken
    global web_get
    title = 'London congestion charge'
    web_get = lambda params: {
        'query': { 'pages': { 1: { 'revisions': [{
            '*': "'''" + title + "'''"
            }]}}
    }}
    assert get_case_from_content(title) == title

def get_case_from_content(title):
    ret = web_get(content_params + urlquote(title))
    rev = ret['query']['pages'].values()[0]['revisions'][0]
    content = rev['*']
    start = content.lower().find("'''" + title.replace('_', ' ').lower() + "'''")
    if start != -1:
        return content[start+3:start+3+len(title)]

@app.route('/diff/<q>')
def diff_view(q):
    title = request.args.get('title')
    return render_template('diff.html', q=q, title=title)

def get_page(title, q, linkto=None):
    ret = web_get(content_params + urlquote(title))
    rev = ret['query']['pages'].values()[0]['revisions'][0]
    content = rev['*']
    timestamp = rev['timestamp']
    timestamp = ''.join(c for c in timestamp if c.isdigit())

    try:
        (content, replacement) = find_link_in_content(q, content, linkto)
    except NoMatch:
        return None

    summary = "link [[%s]] using [[User:Edward/Find link|Find link]]" % replacement
    #text = "title: %s\nq: %s\nsummary: %s\ntimestamp: %s\n\n%s" % (title, q, timestamp, summary, content)

    start_time = datetime.now().strftime("%Y%m%d%H%M%S")
    return render_template('find_link.html',
            urlquote=urlquote,
            start_time=start_time,
            content=content,
            title=title, summary=summary, timestamp=timestamp)

def case_flip(s):
    if s.islower():
        return s.upper()
    if s.isupper():
        return s.lower()
    return s
def case_flip_first(s):
    return case_flip(s[0]) + s[1:]

def match_type(q, snippet):
    q = q.replace(u'\u2013', '-')
    snippet = snippet.replace(u'\u2013', '-')
    if q in snippet or case_flip_first(q) in snippet:
        return 'exact'
    match = None
    if q.lower() in snippet.lower():
        match = 'case_mismatch'
    if match != 'exact' and q.endswith('y'):
        if q[:-1] in snippet or case_flip_first(q[:-1]) in snippet:
            return 'exact'
    elif match is None:
        if q[:-1].lower() in snippet.lower():
            match = 'case_mismatch'
    return match
 
def test_match_type():
    assert match_type('foo', 'foo') == 'exact'
    assert match_type('foo', 'bar') == None
    assert match_type('bar', 'foo bar baz') == 'exact'
    assert match_type('clean coal technology', 'foo clean coal technologies baz') == 'exact'
    assert match_type('bar', 'foo Bar baz') == 'exact'
    assert match_type('bar', 'foo BAR baz') == 'case_mismatch'
    assert match_type('foo-bar', 'aa foo-bar cc') == 'exact'
    assert match_type(u'foo\u2013bar', 'aa foo-bar cc') == 'exact'

@app.route("/<q>")
def findlink(q, title=None, message=None):

    q_trim = q.strip('_')
    if not message and (' ' in q or q != q_trim):
        return redirect(url_for('findlink', q=q.replace(' ', '_').strip('_'), message=message))
    q = q.replace('_', ' ').strip()
    try:
        redirect_to = get_wiki_info(q)
    except Missing:
        return render_template('index.html', message=q + " isn't an article")
    #if redirect_to:
    #    return redirect(url_for('findlink', q=redirect_to.replace(' ', '_')))
    if redirect_to:
        if q[0].isupper():
            redirect_to = redirect_to[0].upper() +  redirect_to[1:]
        elif q[0].islower():
            redirect_to = redirect_to[0].lower() +  redirect_to[1:]
    this_title = q[0].upper() + q[1:]
    (totalhits, search) = wiki_search(q)
    (articles, redirects) = wiki_backlink(redirect_to or q)
    cm = set()
    for cat in set(['Category:' + this_title] + cat_start(q)):
        cm.update(categorymembers(cat))
    norm_q = norm(q)
    norm_match_redirect = set(r for r in redirects if norm(r) == norm_q)
    longer_redirect = set(r for r in redirects if q.lower() in r.lower())

    articles.add(this_title)
    if redirect_to:
        articles.add(redirect_to[0].upper() + redirect_to[1:])
    for r in norm_match_redirect | longer_redirect:
        articles.add(r)
        a2, r2 = wiki_backlink(r)
        articles.update(a2)
        redirects.update(r2)

    longer = all_pages(this_title)
    lq = q.lower()
    for doc in search:
        lt = doc['title'].lower()
        if lt != lt and lq in lt:
            articles.add(doc['title'])
            (more_articles, more_redirects) = wiki_backlink(doc['title'])
            articles.update(more_articles)
            if doc['title'] not in longer:
                longer.append(doc['title'])

    search = [doc for doc in search if doc['title'] not in articles and doc['title'] not in cm]
    if search:
        disambig = set(find_disambig([doc['title'] for doc in search]))
        search = [doc for doc in search if doc['title'] not in disambig]
    # and (doc['title'] not in links or this_title not in links[doc['title']])]
        for doc in search:
            without_markup = doc['snippet'].replace("<span class='searchmatch'>", "").replace("</span>", "").replace('  ', ' ')
            doc['match'] = match_type(q, without_markup)
            doc['snippet'] = Markup(doc['snippet'])
    return render_template('index.html', q=q,
        totalhits = totalhits,
        message = message,
        results = search,
        urlquote = urlquote,
        commify = commify,
        longer_titles = longer,
        redirect_to = redirect_to,
        norm_match_redirect = norm_match_redirect,
        case_flip_first = case_flip_first)

@app.route("/favicon.ico")
def favicon():
    return redirect(url_for('static', filename='Link_edit.png'))

@app.route("/new_pages")
def newpages():
    np = web_get(new_page_params)['query']['recentchanges']
    return render_template('new_pages.html', new_pages=np)

@app.route("/find_link/<q>")
def bad_url(q):
    return findlink(q)

def wiki_space_norm(s):
    return s.replace('_', ' ').strip()

@app.route("/")
def index():
    title = request.args.get('title')
    q = request.args.get('q')
    linkto = request.args.get('linkto')
    if title and q:
        q = wiki_space_norm(q)
        title = wiki_space_norm(title)
        if linkto:
            linkto = wiki_space_norm(linkto)
        reply = get_page(title, q, linkto)
        if reply is None:
            redirects = list(wiki_redirects(q))
            for r in redirects:
                reply = get_page(title, r, linkto=q)
                if reply:
                    return reply
            return findlink(q.replace(' ', '_'), title=title, message=q + ' not in ' + title)
        else:
            return reply
    if q:
        return redirect(url_for('findlink', q=q.replace(' ', '_').strip('_')))
    return render_template('index.html')

if __name__ == "__main__":
    app.run(host='0.0.0.0', debug=True)
