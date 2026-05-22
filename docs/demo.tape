# gsm demo recording
# Install: brew install charmbracelet/tap/vhs
# Record: vhs docs/demo.tape
# Output: docs/assets/demo.gif

Output docs/assets/demo.gif

Set Shell "bash"
Set FontSize 14
Set Width 900
Set Height 500
Set Theme "Catppuccin Mocha"
Set Padding 20

Type "gsm"
Enter
Sleep 2s

# Show the menu
Screenshot docs/assets/menu.png

Sleep 1s
Type "0"
Enter
Sleep 500ms

# Show domain onboarding
Type "gsm domains add --file domains.txt --dry-run"
Enter
Sleep 2s

# Show user generation
Type "gsm users gen --domain example.com --count 5 --dry-run"
Enter
Sleep 2s

# Show health check
Type "gsm health --domain example.com"
Enter
Sleep 2s

# Show doctor
Type "gsm doctor"
Enter
Sleep 3s
