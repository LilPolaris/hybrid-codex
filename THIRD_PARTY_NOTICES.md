# Third-party code

This project integrates, rather than replaces, the following MIT-licensed projects:

- [Rakeem-C/cursor-chatgpt-web](https://github.com/Rakeem-C/cursor-chatgpt-web),
  pinned to `b3733e277f5523909845a5555c11a122e4900742` as a Git submodule.
- [miuuyy/codex-chatgpt-web](https://github.com/miuuyy/codex-chatgpt-web),
  the upstream browser/launcher implementation. The launcher descriptor v2
  adaptation in our patch was derived from its 4.0.7 source layout and tested
  against an existing 4.0.8 launcher/runtime.

The submodule retains its LICENSE and LICENSES directory. Compatibility patch
code derived from that implementation is also covered by this notice:

> MIT License
>
> Copyright (c) 2026 codex-chatgpt-web contributors
>
> Permission is hereby granted, free of charge, to any person obtaining a copy
> of this software and associated documentation files (the "Software"), to deal
> in the Software without restriction, including without limitation the rights
> to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
> copies of the Software, and to permit persons to whom the Software is
> furnished to do so, subject to the following conditions:
>
> The above copyright notice and this permission notice shall be included in all
> copies or substantial portions of the Software.
>
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
> IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
> FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
> AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
> LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
> OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
> SOFTWARE.
