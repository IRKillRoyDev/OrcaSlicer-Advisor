use framework "AppKit"
use scripting additions

property serverPid : 0
property didOpen : false
property safariBlocked : false

on openNewWindow:sender
	set safariBlocked to false
	set didOpen to openAdvisor()
end openNewWindow:

on projectDir()
	set appPath to POSIX path of (path to me)
	if appPath ends with "/" then set appPath to text 1 thru -2 of appPath
	set oldDelims to AppleScript's text item delimiters
	set AppleScript's text item delimiters to "/"
	set parts to text items of appPath
	if (count of parts) < 2 then error "Could not find the project folder."
	set parts to items 1 thru -2 of parts
	set parentPath to parts as text
	set AppleScript's text item delimiters to oldDelims
	return parentPath
end projectDir

on appletPid()
	return (do shell script "/bin/ps -o ppid= -p $$ | /usr/bin/tr -d ' '") as integer
end appletPid

on startServer()
	set root to projectDir()
	set boot to root & "/boot-advisor.sh"
	-- Parentheses, redirects, and & are required. A plain do shell script
	-- waits forever if the server keeps the script's output pipe open.
	do shell script "(/usr/bin/nohup /bin/bash " & quoted form of boot & " " & quoted form of root & " " & (appletPid() as text) & " >/dev/null 2>&1 &)"
end startServer

on stopServer()
	set root to projectDir()
	try
		do shell script "/bin/kill $(/bin/cat " & quoted form of (root & "/work/server.pid") & ") >/dev/null 2>&1 || true"
	end try
	set serverPid to 0
end stopServer

on installMenus()
	set bar to current application's NSApp's mainMenu()
	set fileTop to bar's itemWithTitle:"File"
	if fileTop is missing value then
		set fileMenu to current application's (NSMenu's alloc()'s initWithTitle:"File")
		set fileTop to current application's (NSMenuItem's alloc()'s initWithTitle:"File" action:(missing value) keyEquivalent:"")
		fileTop's setSubmenu:fileMenu
		bar's insertItem:fileTop atIndex:1
	end if
	set fileMenu to fileTop's submenu()
	if (fileMenu's itemWithTitle:"New Window") is missing value then
		set windowAction to "openNewWindow" & character id 58
		-- No Command-N shortcut. macOS treats that as the automatic new-document action.
		set newItem to current application's (NSMenuItem's alloc()'s initWithTitle:"New Window" action:windowAction keyEquivalent:"")
		newItem's setTarget:me
		fileMenu's insertItem:newItem atIndex:0
	end if
end installMenus

on openAdvisor()
	try
		-- Wait for Safari to create the window, then set that window's address.
		-- Activating Safari alone brings forward whatever window was already in front.
		tell application "Safari"
			set beforeIds to {}
			repeat with w in windows
				set end of beforeIds to (id of w as integer)
			end repeat
			make new document
			set targetId to 0
			repeat with w in windows
				set wid to (id of w as integer)
				if beforeIds does not contain wid then
					set targetId to wid
					exit repeat
				end if
			end repeat
			if targetId is 0 then error "Safari did not open a new window."
			repeat with w in windows
				if (id of w as integer) is targetId then
					set URL of «class cTab» of w to "http://127.0.0.1:8777/"
					exit repeat
				end if
			end repeat
			activate
		end tell
		return true
	on error messageText number errorNumber
		if errorNumber is -1743 then
			-- One explanation. Idle must not ask again every second.
			if safariBlocked then return false
			set safariBlocked to true
			try
				do shell script "open " & quoted form of "x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?Privacy_Automation"
			end try
			display alert "Allow OrcaSlicer Advisor to control Safari" message "System Settings is open to Automation. Turn on Safari for OrcaSlicer Advisor, then choose File → New Window."
		else
			display alert "OrcaSlicer Advisor" message messageText
		end if
		return false
	end try
end openAdvisor

on run
	set serverPid to 0
	set didOpen to false
	try
		installMenus()
		startServer()
	on error messageText
		display alert "OrcaSlicer Advisor" message messageText
		quit
	end try
end run

on reopen
	if didOpen is false and safariBlocked is false then
		try
			do shell script "/usr/bin/curl -sf -o /dev/null --max-time 0.4 http://127.0.0.1:8777/"
			set didOpen to openAdvisor()
		end try
	end if
end reopen

on idle
	if didOpen is false and safariBlocked is false then
		try
			do shell script "/usr/bin/curl -sf -o /dev/null --max-time 0.4 http://127.0.0.1:8777/"
			set didOpen to openAdvisor()
		end try
	end if
	return 1
end idle

on quit
	stopServer()
	continue quit
end quit
