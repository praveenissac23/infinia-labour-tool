# Infinia - one signature on every email, whatever app sends it (Outlook PC, Mac, webmail, phone).
# A mail-flow rule adds the new signature (white badge logo, department, link) at the server when an email
# goes out WITHOUT the Infinia signature. Emails already signed in Outlook / webmail are left alone, so no
# email gets two. Run in Windows PowerShell:  Connect-ExchangeOnline  first (admin sign-in).

$logo = "https://app.infinia.ae/portal/sig/infinia-logo-badge-s.gif"
$html = @"
<br><table cellpadding="0" cellspacing="0" border="0" style="font-family:Arial,Helvetica,sans-serif;border-collapse:collapse;margin-top:10px;">
<tr><td colspan="2" style="font-size:13px;color:#1E2124;padding:0 0 8px 0;">Thanks &amp; Regards,</td></tr>
<tr><td valign="middle" style="padding:0 18px 0 0;"><a href="https://www.infinia.ae"><img src="$logo" width="200" height="43" alt="Infinia Contracting" style="display:block;border:0;width:200px;height:43px;"></a></td>
<td valign="middle" style="padding:2px 0 2px 18px;border-left:2px solid #C0392B;">
<div style="font-size:16px;font-weight:bold;color:#1E2124;">%%Department%%</div>
<div style="font-family:Georgia,'Times New Roman',serif;font-size:13px;font-style:italic;color:#9A7B4F;margin-top:3px;">Every space should reflect your story.</div>
<div style="font-size:8.5px;letter-spacing:1.6px;color:#6B7075;margin-top:8px;">DESIGN &amp; BUILD <span style="color:#C0392B;">&#9679;</span> LUXURY VILLAS <span style="color:#C0392B;">&#9679;</span> SWIMMING POOLS <span style="color:#C0392B;">&#9679;</span> FIT-OUT</div>
<div style="font-size:11px;margin-top:6px;color:#8A8178;"><a href="https://www.infinia.ae" style="color:#C0392B;font-weight:bold;">www&#46;infinia&#46;ae</a>&nbsp;&nbsp;|&nbsp;&nbsp;M09, Bin Bishr Building, Abu Hail, Dubai</div>
</td></tr></table>
"@

$name = "Infinia signature (phones)"
$p = @{
  ApplyHtmlDisclaimerText            = $html
  ApplyHtmlDisclaimerLocation        = "Append"
  ApplyHtmlDisclaimerFallbackAction  = "Wrap"
  FromScope                          = "InOrganization"
  ExceptIfSubjectOrBodyContainsWords = "reflect your story"
  Priority                           = 0
}
if (Get-TransportRule -Identity $name -ErrorAction SilentlyContinue) {
  Set-TransportRule -Identity $name @p
} else {
  New-TransportRule -Name $name @p
}
Enable-TransportRule -Identity $name
Get-TransportRule -Identity $name | Format-List Name,State,Priority,FromScope,ExceptIfSubjectOrBodyContainsWords
Write-Host "Done - every email sent without the Infinia signature now gets it." -ForegroundColor Green
