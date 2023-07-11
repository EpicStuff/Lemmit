# Lemmit

A Reddit-to-Lemmy cross-poster.

## Known bugs:
- When a time-out occurs on a post, it will not be posted again. Often, the post created successfully, but something goes wrong in the gateway. Proper solution would be to check afterwards.
- Some community names are too long for Lemmy, and cant be indexed.

## To do:
- use json feed and drop FeedAgent
- Add a sticky to each community, explaining Lemmit is a Bot-service, and link to any known **non-botty** alternatives. This will also allow Lemmy users to suggest proper alternatives, since bots aren't that smart.
- Disable deleted Communities in DB
- Allow for removal of communities:
  - When failing to post, check if still exist. If not, set enabled to False
  - Alert the bot through private message
  - Check when requesting
- MORE TESTS!
- Create a watcher that periodically checks for updates (edits / deletes) on reddit post and sync those:
  * 1 hour, day, week, month after posting.
  * Automatically when reported (Unless queued in last hour, to prevent abuse)

## Won't do:
- Toggle between copying **New** or just the **Hot** posts
  * Not feasible with the amount of subreddits that are being monitored.

## Maybe later
- Have a hardcoded set of subs, rather than working through a request community, for running on other instances.
