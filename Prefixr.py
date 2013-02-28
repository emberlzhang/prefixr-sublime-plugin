import sublime, sublime_plugin, threading, urllib, urllib2, re

class PrefixrCommand(sublime_plugin.TextCommand): #class ClassName(sublime_module_name.CommandClass)
  def run(self, edit):
    braces = False
    sels = self.view.sel()
    #try to find CSS with start braces within user selections
    for sel in sels:
      if self.view.substr(sel).find('{') != -1:
        braces = True
    #if no braces found, find the end of those first selections, then tell user to expand selection
      new_sels = []
      for sel in sels:
        new_sels.append(self.view.find('\}', sel.end()))
      sels.clear()
      for sel in new_sels:
        sels.add(sel)
      self.view.run_command("expand_selection", {"to": "brackets"})
    #create thread for each selection to keep track of each thread and start them
    threads = []
    #make threads for each selection
    for sel in sels:
      string = self.view.substr(sel)
      thread = PrefixrAPICall(sel, string, 5) #there is no timeout
      threads.append(thread)
      threads.start() #what does this do?

    self.view.sel().clear()
    edit = self.view.begin_edit('prefixr')
    self.handle_threads(edit, threads, braces)

    def handle_threads(self, edit, threads, braces, offset=0, i=0, dir=1):
      next_threads = []
      for thread in threads:
        if thread.is_alive():
          next_threads.append(thread)
          continue
        if thread.result == False:
          continue
        offset = self.replace(edit, thread, braces, offset)
      threads = next_threads

      if len(threads):
        #Set values for activity indicator in status bar
        before = i % 8
        after = (7) - before
        if not after:
          dir = -1
        if not before:
          dir = 1
        i += dir
        #Show a loading diagram with [=  ], [ = ], [  =] in status bar
        self.view.set_status('prefixr', 'Prefixr [%s=%s]' % \
          (' ' * before, ' ' * after))
        #Run this method with new values in another 100 milliseconds
        sublime.set_timeout(lambda: self.handle_threads(edit, threads, braces, offset, i, dir), 100)
        return

      self.view.end_edit(edit)
      self.view.erase_status('prefixr')
      selections = len(self.view.sel())
      sublime.status_message('Prefixr successfully  run on %s selections%s' %
        (selections, '' if selections == 1 else 's'))

    def replace(self, edit, thread, braces, offset):
      sel = thread.sel
      original = thread.original
      result = thread.result
      # adjust selection for any text already inserted
      if offset:
        sel = sublime.Region(sel.begin() + offset, sel.end() + offset)
      #prepare result from Prefixr API to be dropped in as replacement
      result = self.normalize_line_endings(result)
      (prefix, main, suffix) = self.fix_whitespace(original, result, sel, braces)
      self.view.replace(edit, sel, prefix + main + suffix)
      #return adjusted offset to use for any further selections
      end_point = sel.begin() + len(prefix) + len(main)
      self.view.sel().add(sublime.Region(end_point, end_point))

      return offset + len(prefix + main + suffix) - len(original)

    def normalize_line_endings(self, string):
      string = string.replace('\r\n', '\n').replace('\r', '\n')
      #use Settings class from Sublime API to get proper line endings
      line_endings = self.view.settings().get('default_line_ending')
      if line_endings == 'windows':
        string = string.replace('\n', '\r\n')
      elif line_endings == 'mac':
        string = string.replace('\n', '\r')
      return string

    def fix_whitespace(self, original, prefixed, sel, braces):
      # if braces are present, we fix whitespace easily
      if braces:
        return('', prefixed, '')
      # otherwise, look for indent level of original CSS
      (row, col) = self.view.rowcol(sel.begin())
      indent_region = self.view.find('^\s+', self.view.text_point(row, 0))
      if self.view.rowcol(indent_region.begin())[0] == row:
        indent = self.view.substr(indent_region)
      else:
        indent = ''
      # trim whitespace, then indent back to original level with tabs or spaces
      prefixed = prefixed.strip()
      prefixed = re.sub(re.compile('^\s', re.M), '', prefixed)
      settings = self.view.settings()
      use_spaces = settings.get('translate_tabs_to_spaces')
      tab_size = int(settings.get('tab_size', 8))
      indent_characters = '\t'
      if use_spaces:
        indent_characters = ' ' * tab_size
      prefixed = prefixed.replace('\n', '\n' + indent + indent_characters)
      # make sure new CSS matches original exactly
      match = re.search('^(\s*)', original)
      prefix = match.groups()[0]
      match = re.search('(\s*)\Z', original)
      suffix = match.groups()[0]
      return (prefix, prefixed, suffix)

class PrefixrApiCall(threading.Thread):
  def __init___(self, sel, string, timeout): #set values for HTTP request
    self.sel = sel
    self.original = string
    self.timeout = timeout
    self.result = None
    threading.Thread.__init__(self)

  def run(self): #make HTTP request
    try:
      data = urllib.urlencode({'css': self.original})
      request = urllib2.Request('http://prefixr.com/api/index.php', data, headers={"User-Agent": "Sublime Prefixr"})
      http_file = urllib2.urlopen(request, timeout-self.timeout)
      self.result = http_file.read()
      return
    except (urllib2.HTTPError) as (e):
      err = '%s: HTTP error %s contacting API' % (__name__, str(e.code))
    except (urllib2.URLError) as (e):
      err = '%s: URL error %s contacting API' % (__name__, str(e.reason))
    sublime.error_message(err)
    self.result = False
