// node_packer_decode.js
// Decode an anime-site packed jwplayer script (eval(function(p,a,c,k,e,d){...}))
// and print the resolved stream URL.
//
// Usage:  node node_packer_decode.js <packed_script_file.js>
// Prints: SETUP_FILE:<url>   (the real m3u8/mp4)
//
// How to get <packed_script_file.js>:
//   1. fetch the iframe page (e.g. otakuhg.site/e/<id>)
//   2. extract the balanced-paren eval(...) block (track ( ) depth, skip string literals)
//   3. write it to a file, pass that file path as argv[2]
//
// Why node and not a regex: the packer's token scheme is base-a encoded with
// nested replaces; running the real decoder is ~10 lines and always correct.

const fs = require('fs');
const file = process.argv[2];
if (!file) { console.log('ERR: pass a file path'); process.exit(1); }
const block = fs.readFileSync(file, 'utf8');

// Hook jwplayer.setup to capture sources[0].file
global.jwplayer = function () {
  return {
    key: '',
    setup: function (cfg) {
      const s = cfg && cfg.sources && cfg.sources[0] && cfg.sources[0].file;
      console.log('SETUP_FILE:' + (s || 'NONE'));
    },
  };
};
// Minimal stubs so the script doesn't crash on missing browser globals
global.document = { getElementById: function () { return {}; } };
global.$ = function () { return {}; };
global.window = global;

try {
  eval(block);
} catch (e) {
  // Some scripts throw after setting up the player; that's fine if SETUP_FILE printed.
  console.log('ERR:' + e.message);
}
