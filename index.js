const { chromium } = require('playwright');
const TelegramBot = require('node-telegram-bot-api');
const fs = require('fs');

const TOKEN = '8596594907:AAHUQjk-ik3LGV7kI-4XhCn-fw1T-FHo6wU';
const CHAT = '-1003179573402';
const URL = 'https://1xlite-7636770.bar/ru/live/baccarat';
const LAST_NUMBER_FILE = './last_number.txt';

const bot = new TelegramBot(TOKEN, { polling: false });

let lastMessageId = null;
let lastMessageText = '';
let lastGameNumber = '0';

if (fs.existsSync(LAST_NUMBER_FILE)) {
    lastGameNumber = fs.readFileSync(LAST_NUMBER_FILE, 'utf8');
    console.log('Загружен последний номер:', lastGameNumber);
}

function formatCards(cards) {
    return cards.join('');
}

function determineTurn(playerCards, bankerCards) {
    if (playerCards.length === 2 && bankerCards.length === 2) return 'player';
    if (playerCards.length === 3 && bankerCards.length === 2) return 'banker';
    if (playerCards.length === 2 && bankerCards.length === 3) return 'player';
    return null;
}

async function sendOrEditTelegram(newMessage) {
    if (!newMessage || newMessage === lastMessageText) return;
    try {
        if (lastMessageId) {
            await bot.editMessageText(newMessage, {
                chat_id: CHAT,
                message_id: lastMessageId
            });
        } else {
            const msg = await bot.sendMessage(CHAT, newMessage);
            lastMessageId = msg.message_id;
        }
        lastMessageText = newMessage;
    } catch (e) {
        console.log('TG error:', e.message);
    }
}

// Функция поиска стола с таймером (живая игра)
async function findLiveGame(page) {
    const games = await page.$$('.dashboard-game');

    for (const game of games) {
        const hasTimer = await game.$('.dashboard-game-info__time') !== null;
        const isFinished = await game.evaluate(el => {
            const period = el.querySelector('.dashboard-game-info__period');
            return period?.textContent.includes('Игра завершена') ?? false;
        });

        if (hasTimer && !isFinished) {
            const link = await game.$('a[href*="/ru/live/baccarat/"]');
            if (link) {
                return await link.getAttribute('href');
            }
        }
    }
    return null;
}

async function getCards(page) {
    const playerBlock = await page.$('.baccarat-player:not(.baccarat-player--is-reversed) .baccarat-player__cards');
    const player = playerBlock ? await playerBlock.$$eval('li.baccarat-player__card-box', cards => {
        return cards.map(c => {
            const rankEl = c.querySelector('.baccarat-card__rank');
            if (!rankEl) return null;
            const rank = rankEl.textContent.trim();
            const suitIcon = c.querySelector('.baccarat-card__suit');
            let suit = '';
            if (suitIcon) {
                if (suitIcon.className.includes('spades')) suit = '♠️';
                else if (suitIcon.className.includes('hearts')) suit = '♥️';
                else if (suitIcon.className.includes('clubs')) suit = '♣️';
                else if (suitIcon.className.includes('diamonds')) suit = '♦️';
            }
            return rank + suit;
        }).filter(c => c !== null).slice(0, 3);
    }) : [];

    const bankerBlock = await page.$('.baccarat-player--is-reversed .baccarat-player__cards');
    const banker = bankerBlock ? await bankerBlock.$$eval('li.baccarat-player__card-box', cards => {
        return cards.map(c => {
            const rankEl = c.querySelector('.baccarat-card__rank');
            if (!rankEl) return null;
            const rank = rankEl.textContent.trim();
            const suitIcon = c.querySelector('.baccarat-card__suit');
            let suit = '';
            if (suitIcon) {
                if (suitIcon.className.includes('spades')) suit = '♠️';
                else if (suitIcon.className.includes('hearts')) suit = '♥️';
                else if (suitIcon.className.includes('clubs')) suit = '♣️';
                else if (suitIcon.className.includes('diamonds')) suit = '♦️';
            }
            return rank + suit;
        }).filter(c => c !== null).slice(0, 3);
    }) : [];

    const pScore = await page.$eval('.baccarat-player:not(.baccarat-player--is-reversed) .baccarat-player__number', el => el.textContent).catch(() => '0');
    const bScore = await page.$eval('.baccarat-player--is-reversed .baccarat-player__number', el => el.textContent).catch(() => '0');

    return { player, banker, pScore, bScore };
}

async function monitorGame(page, gameNumber) {
    let lastCards = { player: [], banker: [], pScore: '0', bScore: '0' };

    while (true) {
        const cards = await getCards(page);

        const isFinished = await page.evaluate(() => {
            const el = document.querySelector('.dashboard-game-info__period');
            return el && el.textContent.includes('Игра завершена');
        });

        if (isFinished) {
            const total = parseInt(cards.pScore) + parseInt(cards.bScore);
            const winner = cards.pScore > cards.bScore ? 'П1' : (cards.bScore > cards.pScore ? 'П2' : 'X');
            const noDrawFlag = cards.player.length === 2 && cards.banker.length === 2 ? '#R ' : '';

            let message;
            if (cards.pScore > cards.bScore) {
                message = `#N${gameNumber} ✅${cards.pScore} (${formatCards(cards.player)}) - ${cards.bScore} (${formatCards(cards.banker)}) ${noDrawFlag}#${winner} #T${total}`;
            } else if (cards.bScore > cards.pScore) {
                message = `#N${gameNumber} ${cards.pScore} (${formatCards(cards.player)}) - ✅${cards.bScore} (${formatCards(cards.banker)}) ${noDrawFlag}#${winner} #T${total}`;
            } else {
                message = `#N${gameNumber} ${cards.pScore} (${formatCards(cards.player)}) 🔰 ${cards.bScore} (${formatCards(cards.banker)}) ${noDrawFlag}#${winner} #T${total}`;
            }

            await sendOrEditTelegram(message);
            console.log(`Игра #${gameNumber} завершена`);
            return; // Выход из monitorGame
        }

        if (cards.player.length > 0 && cards.banker.length > 0) {
            const turn = determineTurn(cards.player, cards.banker);

            let message;
            if (turn === 'player') {
                message = `⏱№${gameNumber} 👉${cards.pScore}(${formatCards(cards.player)}) -${cards.bScore} (${formatCards(cards.banker)})`;
            } else if (turn === 'banker') {
                message = `⏱№${gameNumber} ${cards.pScore}(${formatCards(cards.player)}) -👉${cards.bScore} (${formatCards(cards.banker)})`;
            } else {
                message = `⏱№${gameNumber} ${cards.pScore}(${formatCards(cards.player)}) -${cards.bScore} (${formatCards(cards.banker)})`;
            }

            const cardsChanged = 
                JSON.stringify(cards.player) !== JSON.stringify(lastCards.player) ||
                JSON.stringify(cards.banker) !== JSON.stringify(lastCards.banker) ||
                cards.pScore !== lastCards.pScore ||
                cards.bScore !== lastCards.bScore;

            if (cardsChanged) {
                await sendOrEditTelegram(message);
                lastCards = { ...cards };
            }
        }

        await page.waitForTimeout(2000);
    }
}

async function run() {
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();

    await page.goto(URL);
    console.log('Ищем живой стол с таймером...');

    let liveLink = null;
    while (!liveLink) {
        liveLink = await findLiveGame(page);
        if (!liveLink) {
            await page.waitForTimeout(1000); // быстрая прокрутка
        }
    }

    console.log('Найден живой стол:', liveLink);
    await page.click(`a[href="${liveLink}"]`);
    await page.waitForTimeout(3000);

    let gameNumber = await page.evaluate(() => {
        const el = document.querySelector('.dashboard-game-info__additional-info');
        return el ? el.textContent.trim() : null;
    });

    if (!gameNumber) {
        gameNumber = (parseInt(lastGameNumber) + 1).toString();
        console.log('Номер не найден, используем следующий:', gameNumber);
    } else {
        console.log('Найден номер стола:', gameNumber);
    }

    lastGameNumber = gameNumber;
    fs.writeFileSync(LAST_NUMBER_FILE, gameNumber);

    let attempts = 0;
    let cards = { player: [], banker: [] };
    while (attempts < 12 && (cards.player.length === 0 || cards.banker.length === 0)) {
        await page.waitForTimeout(5000);
        cards = await getCards(page);
        attempts++;
    }

    if (cards.player.length > 0 && cards.banker.length > 0) {
        await monitorGame(page, gameNumber);
    }

    await browser.close();
    lastMessageId = null;
    lastMessageText = '';
}

// Бесконечный цикл
(async () => {
    console.log('Бот запущен. Последний номер:', lastGameNumber);
    while (true) {
        await run();
    }
})();