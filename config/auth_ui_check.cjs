// Execute the rendered home-page script with a minimal DOM and mocked API.
// Checks event wiring and auth state transitions without using a real account.
const vm = require('node:vm');
const assert = require('node:assert/strict');
let input = '';
process.stdin.on('data', chunk => input += chunk);
process.stdin.on('end', async () => {
  try {
    const { script, elements, entry } = JSON.parse(input);
    class Element {
      constructor(attrs = {}) {
        this.attrs = attrs; this.value = ''; this.textContent = ''; this.disabled = false;
        this.dataset = {tab: attrs['data-tab']}; this.listeners = {};
        const classes = new Set((attrs.class || '').split(' '));
        this.classList = {
          add: c => classes.add(c), remove: c => classes.delete(c), contains: c => classes.has(c),
          toggle(c, force) { const on = force === undefined ? !classes.has(c) : force; on ? classes.add(c) : classes.delete(c); return on; }
        };
      }
      addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); }
      async fire(type) { for (const fn of this.listeners[type] || []) await fn({preventDefault(){},currentTarget:this,target:this}); }
      click() { return this.fire('click'); }
      focus() {} scrollIntoView() {} setAttribute(k,v) {this.attrs[k]=v;} getAttribute(k){return this.attrs[k];}
      querySelector() { return this.button ||= new Element(); }
      querySelectorAll(){return [];}
      closest(){return this.parent;}
    }
    const nodes = Object.fromEntries(elements.filter(a => a.id).map(a => [a.id,new Element(a)]));
    const tabs = ['register','login'].map(tab => new Element({'data-tab':tab}));
    const tabContainer = new Element();
    nodes['public-menu-toggle'].parent = nodes['public-nav'];
    nodes['dashboard-menu-toggle'].parent = new Element();
    const storage = new Map(); let reloads = 0, mode = 'ok', requests = 0;
    if (entry === 'signup') { storage.set('jengaAccessToken', 'existing-access'); storage.set('jengaRefreshToken', 'existing-refresh'); }
    const profile = {full_name:'Test member',preferred_language:'english',business_profile:{business_name:'Test business',tracking_frequency:'weekly'}};
    const context = vm.createContext({
      document: {
        getElementById: id => nodes[id] || null,
        querySelectorAll: selector => selector === '.tabs button' ? tabs : [],
        querySelector: selector => selector === '.tabs' ? tabContainer : tabs.find(t => selector.includes('"'+t.dataset.tab+'"')),
      },
      sessionStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},
      window:{location:{pathname:entry === 'signup' ? '/signup/' : '/',search:'',reload(){reloads++;}},scrollTo(){}}, URLSearchParams,
      fetch: async url => {
        requests++;
        if(mode === 'offline') throw Error('offline');
        const data = url.includes('auth/login') ? {access:'test-access',refresh:'test-refresh'} : profile;
        return {ok:true,status:200,json:async()=>data};
      },
    });
    vm.runInContext(script, context);
    if (entry === 'signup') {
      await Promise.resolve();
      assert.equal(requests, 0, 'Explicit signup must not restore an existing session');
      assert.equal(nodes['auth-area'].classList.contains('hidden'), false);
      assert.equal(nodes['register-form'].classList.contains('hidden'), false);
      assert.equal(nodes.dashboard.classList.contains('hidden'), true);
      console.log('Explicit signup stays on registration even with stored tokens.');
      return;
    }
    // Dashboard APIs are checked by Django's API tests; isolate UI transitions here.
    vm.runInContext('loadRecentActivity = loadFinancialSummary = loadSafeToSpend = loadGoalPreview = loadRetirementPreview = () => Promise.resolve(true);', context);
    assert.ok(nodes['hero-login'].listeners.click?.length, 'Login entry point must be wired');
    await nodes['hero-login'].click();
    assert.equal(nodes['auth-area'].classList.contains('hidden'),false);
    assert.equal(nodes['login-form'].classList.contains('hidden'),false);
    await nodes['nav-back'].click();
    assert.equal(nodes['auth-area'].classList.contains('hidden'),true);
    await nodes['hero-register'].click();
    assert.equal(nodes['register-form'].classList.contains('hidden'),false);
    await nodes['public-menu-toggle'].click();
    assert.equal(nodes['public-menu-toggle'].attrs['aria-expanded'],'true');
    await nodes['nav-login'].click();
    mode = 'offline';
    await nodes['login-form'].fire('submit');
    assert.equal(nodes['login-form'].querySelector().disabled,false);
    assert.match(nodes.message.textContent,/Could not connect/);
    mode = 'ok';
    await nodes['login-form'].fire('submit');
    assert.equal(storage.get('jengaAccessToken'),'test-access');
    assert.equal(nodes.dashboard.classList.contains('hidden'),false);
    assert.equal(nodes['public-nav'].classList.contains('hidden'),true);
    assert.equal(nodes['auth-area'].classList.contains('hidden'),true);
    await nodes['logout-button'].click();
    assert.equal(storage.size,0); assert.equal(reloads,1);
    console.log('Auth UI: login/signup entry points, menu, failed-request retry, successful login, dashboard visibility, and logout passed.');
  } catch (error) { console.error(error); process.exitCode = 1; }
});
