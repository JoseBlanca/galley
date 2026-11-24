--[[
galley's back links from footnotes to their references (architecture
section 9, "Back links"; the owner, 24 November 2026).

Pandoc's EPUB 3 writer makes each footnote of book.md an
<aside epub:type="footnote" id="fnN"> at the end of its chapter file,
holding the note's text and no number, and its reference a link
<a id="fnrefN">N</a>. This filter puts N at the start of each footnote,
as a link back to "#fnrefN" of class footnote-back with the role
doc-backlink, in the note's first paragraph that is not inside a margin
note's div.

Pandoc 3.14 numbers the footnotes of each chapter file from 1, and starts a
file at each heading of level 1 (its default --split-level), so the filter
counts the notes in the order of the text and starts again at each such
heading. The ids are Pandoc's, not galley's: the epub stage's tests check
that each back link points to its own note's reference, and epubcheck
reports a link to an id no file holds.
]]

-- The heading level at which Pandoc starts a chapter file.
local SPLIT_LEVEL = 1
-- The class of the div of a margin note, which keeps its own line.
local MARGIN_NOTE_CLASS = "margin-note"
-- The class of the back link, Pandoc's own for it in HTML, which tells it
-- from an endnote's back link: its number is Pandoc's, not a word of the
-- book.
local BACK_LINK_CLASS = "footnote-back"

local count = 0

-- The first Para or Plain of `blocks`, depth first, outside a margin
-- note's div; nil when there is none.
local function first_paragraph(blocks)
  for _, block in ipairs(blocks) do
    if block.t == "Para" or block.t == "Plain" then
      return block
    end
    if block.t == "Div" and not block.classes:includes(MARGIN_NOTE_CLASS) then
      local found = first_paragraph(block.content)
      if found then
        return found
      end
    end
  end
  return nil
end

local function back_link(note)
  count = count + 1
  local number = tostring(count)
  local link = pandoc.Link(
    number,
    "#fnref" .. number,
    "",
    pandoc.Attr("", { BACK_LINK_CLASS }, { role = "doc-backlink" })
  )
  local paragraph = first_paragraph(note.content)
  if paragraph then
    paragraph.content:insert(1, pandoc.Space())
    paragraph.content:insert(1, link)
  else
    note.content:insert(1, pandoc.Plain({ link }))
  end
  return note, false
end

local function start_of_file(header)
  if header.level <= SPLIT_LEVEL then
    count = 0
  end
end

function Pandoc(document)
  return document:walk({
    traverse = "topdown",
    Header = start_of_file,
    Note = back_link,
  })
end
