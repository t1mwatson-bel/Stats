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

function getGameNumberByTime() {
    const now = new Date();
    const mskTime = new Date(now.toLocaleString('en-US', { timeZone: 'Europe/Moscow' }));
    
    const currentHours = mskTime.getHours();
    const currentMinutes = mskTime.getMinutes();
    const currentSeconds = mskTime.getSeconds();
    
    const startHour = 3;
    const startMinute = 0;
    
    if (currentHours < startHour || (currentHours === startHour && currentMinutes < startMinute)) {
        return null;
    }
    
    let minutesSinceStart = (currentHours - startHour) * 60 + (currentMinutes - startMinute);
    
    if (currentSeconds < 5) {
        minutesSinceStart -= 1;
    }
    
    return minutesSinceStart + 1;
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

async function findFirstLiveGame(page) {
    const games = await page.$$('.dashboard-game');
    for (const game of games) {
        const hasTimer = await game.$('.dashboard-game-info__time') !== null;
        if (!hasTimer) continue;

        const isFinished = await game.evaluate(el => {
            const period = el.querySelector('.dashboard-game-info__period');
            return period?.textContent.includes('Игра завершена') ?? false;
        });

        if (!isFinished) {
            const link = await game.$('a[href*="/ru/live/baccarat/"]');
            if (link) return await link.getAttribute('href');
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
        
        const isGameOver = await page.evaluate(() => {
            const panel = document.querySelector('.market-grid__game-over-panel');
            if (!panel) return false;
            const caption = panel.querySelector('.ui-caption');
            return caption && caption.textContent.includes('Игра завершена');
        });
        
        if (isGameOver) {
            const cards = await getCards(page);
            
            if (cards.player.length > 0 || cards.banker.length > 0) {
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
            }
            
            await page.waitForTimeout(10000);
            break;
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

// ===== ОСНОВНАЯ ФУНКЦИЯ =====
async function run() {
    let browser;
    let timeout;
    const startTime = Date.now();
    
    try {
        console.log(`\n🟢 Браузер открыт в ${new Date().toLocaleTimeString()}.${new Date().getMilliseconds()}`);
        
        browser = await chromium.launch({ headless: true });
        const page = await browser.newPage();
        
        // Жизнь браузера 60 секунд (ровно 1 минута)
        timeout = setTimeout(async () => {
            if (browser) await browser.close();
        }, 60000);
        
        await page.goto(URL);
        
        let activeLink = null;
        let attempts = 0;
        while (!activeLink && attempts < 10) {
            activeLink = await findFirstLiveGame(page);
            if (!activeLink) {
                await page.waitForTimeout(5000);
                attempts++;
            }
        }
        
        if (!activeLink) return;
        
        await page.click(`a[href="${activeLink}"]`);
        
        // Ждем либо карты, либо завершение (максимум 5 секунд)
        await Promise.race([
            page.waitForSelector('.baccarat-player__cards', { timeout: 5000 }).catch(() => {}),
            page.waitForSelector('.market-grid__game-over-panel', { timeout: 5000 }).catch(() => {})
        ]);
        
        let gameNumber = getGameNumberByTime();
        if (!gameNumber) return;
        
        gameNumber = gameNumber.toString();
        lastGameNumber = gameNumber;
        fs.writeFileSync(LAST_NUMBER_FILE, gameNumber);
        
        // Сразу читаем карты
        let initialCards = await getCards(page);
        
        // Проверяем, не завершилась ли игра
        const gameOverNow = await page.evaluate(() => {
            return document.querySelector('.market-grid__game-over-panel') !== null;
        });

        if (gameOverNow && (initialCards.player.length > 0 || initialCards.banker.length > 0)) {
            const total = parseInt(initialCards.pScore) + parseInt(initialCards.bScore);
            const winner = initialCards.pScore > initialCards.bScore ? 'П1' : (initialCards.bScore > initialCards.pScore ? 'П2' : 'X');
            const noDrawFlag = initialCards.player.length === 2 && initialCards.banker.length === 2 ? '#R ' : '';
            
            let message;
            if (initialCards.pScore > initialCards.bScore) {
                message = `#N${gameNumber} ✅${initialCards.pScore} (${formatCards(initialCards.player)}) - ${initialCards.bScore} (${formatCards(initialCards.banker)}) ${noDrawFlag}#${winner} #T${total}`;
            } else if (initialCards.bScore > initialCards.pScore) {
                message = `#N${gameNumber} ${initialCards.pScore} (${formatCards(initialCards.player)}) - ✅${initialCards.bScore} (${formatCards(initialCards.banker)}) ${noDrawFlag}#${winner} #T${total}`;
            } else {
                message = `#N${gameNumber} ${initialCards.pScore} (${formatCards(initialCards.player)}) 🔰 ${initialCards.bScore} (${formatCards(initialCards.banker)}) ${noDrawFlag}#${winner} #T${total}`;
            }
            
            await sendOrEditTelegram(message);
            await page.waitForTimeout(10000);
            return;
        }
        
        let cardsAttempts = 0;
        let cards = { player: [], banker: [] };
        while (cardsAttempts < 12 && (cards.player.length === 0 || cards.banker.length === 0)) {
            await page.waitForTimeout(5000);
            cards = await getCards(page);
            cardsAttempts++;
        }
        
        if (cards.player.length > 0 && cards.banker.length > 0) {
            await monitorGame(page, gameNumber);
        }
        
    } catch (e) {
        console.log('Ошибка:', e.message);
    } finally {
        if (timeout) clearTimeout(timeout);
        if (browser) {
            await browser.close();
            lastMessageId = null;
            lastMessageText = '';
        }
    }
}

// ===== ЗАДЕРЖКА ДО :58 =====
function getDelayTo58() {
    const now = new Date();
    const seconds = now.getSeconds();
    const milliseconds = now.getMilliseconds();
    const targetSeconds = 58;
    
    let delaySeconds;
    if (seconds < targetSeconds) {
        delaySeconds = targetSeconds - seconds;
    } else {
        delaySeconds = (60 - seconds) + targetSeconds;
    }
    
    return (delaySeconds * 1000) - milliseconds;
}

// ===== ЗАПУСК =====
(async () => {
    console.log('🤖 Бот Baccarat запущен');
    console.log('🎯 Номера по московскому времени (3:00 = #1)');
    console.log('⏱ Запуск в :58 каждой минуты');
    console.log('⏱ Жизнь браузера: 60 секунд');
    
    const initialDelay = getDelayTo58();
    const nextRunTime = new Date(Date.now() + initialDelay);
    console.log(`⏱ Первый запуск через ${(initialDelay/1000).toFixed(3)} секунд`);
    console.log(`⏱ Время первого запуска: ${nextRunTime.toLocaleTimeString()}.${nextRunTime.getMilliseconds()}`);
    
    await new Promise(resolve => setTimeout(resolve, initialDelay));
    console.log('✅ Синхронизировались!');
    
    while (true) {
        const now = new Date();
        console.log(`\n🚀 Запуск браузера в ${now.toLocaleTimeString()}.${now.getMilliseconds()}`);
        
        run();
        
        // Ждем ровно 60 секунд до следующего :58
        await new Promise(resolve => setTimeout(resolve, 60000));
    }
})();