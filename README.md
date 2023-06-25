# Lemmit

A Reddit-to-Lemmy cross-poster.

## Known bugs:
- When a time-out occurs on a post, it will not be posted again. Often, the post created successfully, but something goes wrong in the gateway. Proper solution would be to check afterwards.
- Some community names are too long for Lemmy, and cant be indexed.

## To do:
- Allow for removal of communities:
  - When failing to post, check if still exist. If not, set enabled to False
  - Alert the bot through private message
  - Check when requesting
- MORE TESTS!
- Increase delay between posts when initially setting up a community (benefits both scraping and federating)
- Create a watcher that periodically checks for updates (edits / deletes) on reddit post and sync those:
  * 1 hour, day, week, month after posting.
  * Automatically when reported (Unless queued in last hour, to prevent abuse)
- Have score based system for update frequency (posts/hour + subscribers)

## Won't do:
- Toggle between copying **New** or just the **Hot** posts
  * Not feasible with the amount of subreddits that are being monitored.

## Maybe later
- Have a hardcoded set of subs, rather than working through a request community, for running on other instances.
