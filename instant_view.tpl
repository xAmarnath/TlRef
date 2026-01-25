~version: "2.1"

### 1. Define Target
?exists: //main

### 2. General Config
body:       //main
title:      $body//h1
subtitle:   $body//p[has-class("description")]
subtitle:   $body//div[has-class("hero-section")]/p

# Metadata
site_name:  "Gogram TL Reference"
author:     "AmarnathCJD"

### 3. Cleanup
@remove:    //header
@remove:    //footer
@remove:    //script
@remove:    //style
@remove:    //div[has-class("breadcrumb")]
@remove:    //div[has-class("search-container")]
@remove:    //input
# Remove Layer badge from detail pages (inside article)
@remove:    $body//article//span[contains(text(), "Layer")]/..

### 4. Content Logic

## Hero / Stats (Index)
$hero_stats: $body//div[has-class("hero-section")]/div[last()]
<p>:         $hero_stats
@after(" • "): $hero_stats/div
@remove:     ($hero_stats/div[last()]/@after)[1]

## Badges (General)
$badges:     $body//div[has-class("badges")]
@after(" "): $badges/span

## Lists (Constructors, Methods, Types)
# Define targets first
$item_lists: $body//div[has-class("item-list")]
$list_items: $item_lists/a[has-class("item")]
$item_names: $list_items//span[has-class("item-name")]
$item_descs: $list_items//span[has-class("item-desc")]

# Apply Item Styling
<b>:         $item_names
@after(": "): $item_names

# Transform structure
@wrap(<li>): $list_items
<ul>:        $item_lists

## Code & Syntax
<pre>:       $body//div[has-class("code-block")]
<pre>:       $body//pre[has-class("example-code")]

# Highlighting
$keywords:   $body//span[has-class("keyword")]
$types:      $body//span[has-class("type")]
$strings:    $body//span[has-class("string")]
$comments:   $body//span[has-class("comment")]
$functions:  $body//span[has-class("function")]
$numbers:    $body//span[has-class("number")]
$packages:   $body//span[has-class("package")]

<b>:         $keywords
<b>:         $types
<i>:         $strings
<i>:         $comments
<b>:         $functions
<span>:      $numbers
<span>:      $packages

## Tables (Params, Errors)
$tables:     $body//div[has-class("table-container")]/table
@detach:     $tables
@before_el(./..): $tables
@remove:     $body//div[has-class("table-container")]

## Returns
$returns_div: $body//div[has-class("result-section")]
<p>:          $returns_div
<b>:          $returns_div/h3
@after(" "):  $returns_div/h3

## Related Lists
$rel_list:    $body//ul[has-class("related-list")]
<ul>:         $rel_list
<li>:         $rel_list/li

## About Section
<blockquote>: $body//div[has-class("about-section")]

