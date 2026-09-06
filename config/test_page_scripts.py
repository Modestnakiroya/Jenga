"""Exercise scripts as a page: syntax checks on isolated blocks miss duplicate globals."""
import json
import re
import shutil
import subprocess
from unittest import skipUnless

from django.test import SimpleTestCase


@skipUnless(shutil.which("node"), "Node is needed for browser-script checks")
class PageScriptTests(SimpleTestCase):
    def scripts(self, path):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        return [body for attrs, body in re.findall(r"<script([^>]*)>(.*?)</script>", response.content.decode(), re.S)
                if "application/json" not in attrs]

    def test_all_public_page_scripts_share_valid_global_scope(self):
        for path in ["/", "/signup/", "/profile/", "/goals/", "/partners/", "/partnerships/", "/assistant/", "/insights/", "/sacco/", "/sacco/login/"]:
            with self.subTest(path=path):
                result = subprocess.run(["node", "--check"], input="\n".join(self.scripts(path)), text=True, encoding="utf-8", capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_profile_renders_and_recovers_from_failures(self):
        # Execute real profile/i18n code with only the DOM and API boundary mocked.
        scripts = self.scripts("/profile/")
        source = "\n".join(s for s in scripts if "const DASHBOARD_LABELS" in s or "async function loadProfile" in s)
        harness = r'''
const vm=require('node:vm'), assert=require('node:assert/strict');
const source=JSON.parse(require('node:fs').readFileSync(0,'utf8'));
(async()=>{
 for(const mode of ['member','bank','missing','offline','expired','refresh-only']){
  const nodes={};
  function element(){const classes=new Set(['hidden']);return {textContent:'',checked:false,disabled:false,
    classList:{add:x=>classes.add(x),remove:x=>classes.delete(x),contains:x=>classes.has(x)},
    listeners:{},addEventListener(type,fn){this.listeners[type]=fn;},focus(){},setAttribute(){},replaceChildren(){},append(){}};}
  const document={getElementById:id=>nodes[id] ||=element(),querySelector:()=>element(),querySelectorAll:()=>[],createElement:element,documentElement:{}};
  const profile={full_name:'Test Member',phone_number:'+256700123456',preferred_language:'english',role:mode==='bank'?'bank':'user',business_profile:mode==='missing'?null:{tracking_frequency:'weekly'}};
  const context=vm.createContext({document,window:{location:{}},sessionStorage:{getItem:key=>mode==='refresh-only'?(key==='jengaRefreshToken'?'refresh':null):'token',removeItem(){}},localStorage:{getItem(){return null},setItem(){}},
    sessionFetch:async(url,options)=>{if(options?.method==='PATCH'){const values=JSON.parse(options.body);assert.deepEqual(Object.keys(values).sort(),['email','full_name','preferred_language']);Object.assign(profile,values);}if(mode==='offline')throw Error('offline');return {ok:mode!=='expired',status:mode==='expired'?401:200,json:async()=>profile};}});
  vm.runInContext(source,context);
  await vm.runInContext('loadProfile()',context);
  if(mode==='offline'||mode==='expired')assert.match(nodes['profile-message'].textContent,/Could not connect|session expired/);
  else {assert.equal(nodes['profile-content'].classList.contains('hidden'),false);assert.equal(nodes['profile-name'].textContent,'Test Member');assert.match(nodes['profile-frequency'].textContent,/Weekly|weekly/);
    await nodes['edit-profile'].listeners.click();
    assert.equal(nodes['edit-name'].value,'Test Member');
    nodes['edit-name'].value='Unsaved';
    await nodes['cancel-profile'].listeners.click();
    assert.equal(nodes['profile-name'].textContent,'Test Member');
    await nodes['edit-profile'].listeners.click();
    assert.equal(nodes['edit-name'].value,'Test Member');
    nodes['edit-name'].value='Updated Member';
    nodes['edit-email'].value='member@example.com';
    await nodes['profile-edit-form'].listeners.submit({preventDefault(){}});
    assert.equal(nodes['profile-name'].textContent,'Updated Member');
    assert.equal(nodes['edit-status'].textContent,'Profile updated.');
    assert.equal(nodes['save-profile'].disabled,false);
  }
 }
})().catch(error=>{console.error(error);process.exitCode=1;});
'''
        result = subprocess.run(["node", "-e", harness], input=json.dumps(source), text=True, encoding="utf-8", capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
