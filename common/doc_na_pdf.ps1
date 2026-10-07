# Prevod Word dokumentu (.doc/.rtf) na DOCX a PDF pres nainstalovany MS Word.
# Pouziti: powershell -NoProfile -File doc_na_pdf.ps1 <vstup> <vystup.docx> <vystup.pdf>
#
# Vola extrakce_1_konverze.py pro SPC, ktera SUKL ma jen jako Word (CAVINTON).
#   DOCX = zdroj OBSAHU: Docling ho cte primo ze struktury (tabulky podle
#          bunek, bez odhadu z vzhledu stranky).
#   PDF  = jen pro GUI (odkaz na stranu) a kontroly; Word do nej zapise
#          i strukturni znacky (tagged PDF).
# Word neumi soubezny pristup, proto jeden soubor = jedno spusteni.
param([string]$Vstup, [string]$VystupDocx, [string]$VystupPdf)
$ErrorActionPreference = "Stop"
$word = New-Object -ComObject Word.Application
try {
    $word.Visible = $false
    $word.DisplayAlerts = 0
    # ConfirmConversions=false, ReadOnly=true, AddToRecentFiles=false
    $doc = $word.Documents.Open($Vstup, $false, $true, $false)
    # Automaticke cislovani ("4.8" jako cislovany seznam, ne text) Docling
    # v DOCX nevypise -> sekce nejdou najit (ALMIRAL: 4.8 nenalezena).
    # Prevod cisel na text PRED ulozenim DOCX. PDF se exportuje az potom,
    # vypada stejne.
    $doc.ConvertNumbersToText()
    $doc.SaveAs2($VystupDocx, 16)                  # 16 = wdFormatXMLDocument
    # ExportAsFixedFormat: 17 = PDF, ... DocStructureTags = true (znacky)
    $doc.ExportAsFixedFormat($VystupPdf, 17, $false, 0, 0, 1, 1, 0, $true, $true, 0, $true, $true, $false)
    $doc.Close(0)
} finally {
    $word.Quit()
    [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($word)
}
