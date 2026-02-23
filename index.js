const { chromium } = require('playwright');
const TelegramBot = require('node-telegram-bot-api');
const fs = require('fs');

const TOKEN = '8596594907:AAHUQjk-ik3LGV7kI-4XhCn-fw1T-FHo6wU';
const CHAT = '-1003179573402';
const URL = 'https://1xlite-7636770.bar/ru/live/baccarat';
const LAST_NUMBER_FILE = './last_number.txt';
const BUSY_TABLES_FILE = './busy_tables.txt';

const bot = new TelegramBot(TOKEN, { polling: false });

let lastMessageId = null;
let lastMessageText = '';
let lastGameNumber = '0';
let browserCounter = 0;

if (fs.existsSync(LAST_NUMBER_FILE)) {
    lastGameNumber = fs.readFileSync(LAST_NUMBER_FILE, 'utf8');
    console.log('Загружен последний номер:', lastGameNumber);
}

// ===== ФУНКЦИИ ДЛЯ РАБОТЫ С ЗАНЯТЫМИ ПОЗИЦИЯМИ =====
function getBusyPositions() {
    try {
        if (fs.existsSync(BUSY_TABLES_FILE)) {
            const content = fs.readFileSync(BUSY_TABLES_FILE, 'utf8');
            return new Set(content.split('\n').filter(line => line.startsWith('pos_')));
        }
    } catch (e) {}
    return new Set();
}

function markPositionBusy(position, browserId) {
    try {
        const busy = getBusyPositions();
        busy.add(`pos_${position}`);
        fs.writeFileSync(BUSY_TABLES_FILE, Array.from(busy).join('\n'));
        console.log(`🔒 Позиция ${position} занята браузером ${browserId}`);
    } catch (e) {}
}

function markPositionFree(position) {
    try {
        const busy = getBusyPositions();
        busy.delete(`pos_${position}`);
        fs.writeFileSync(BUSY_TABLES_FILE, Array.from(busy).join('\n'));
        console.log(`🔓 Позиция ${position} освобождена`);
    } catch (e) {}
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
        console.log('✅ Сообщение отправлено');
    } catch (e) {
        console.log('❌ TG error:', e.message);
        try {
            const msg = await bot.sendMessage(CHAT, newMessage);
            lastMessageId = msg.message_id;
            lastMessageText = newMessage;
        } catch (sendError) {}
    }
}

// ===== ПОИСК АКТИВНЫХ СТОЛОВ =====
async function getActiveGames(page) {
    const games = await page.$$('.dashboard-game');
    const activeGames = [];
    
    for (let i = 0; i < games.length; i++) {
        const game = games[i];
        
        const isFinished = await game.evaluate(el => {
            const period = el.querySelector('.dashboard-game-info__period');
            return period?.textContent.includes('Игра завершена') ?? false;
        });

        if (!isFinished) {
            const link = await game.$('a[href*="/ru/live/baccarat/"]');
            if (link) {
                const href = await link.getAttribute('href');
                activeGames.push({
                    index: i,
                    href,
                    element: game
                });
            }
        }
    }
    
    return activeGames;
}

// ===== ПОИСК СВОБОДНОЙ ПОЗИЦИИ =====
async function findFreePosition(page, browserId) {
    console.log(`🔍 Браузер ${browserId} ищет свободную позицию...`);
    
    const activeGames = await getActiveGames(page);
    const busyPositions = getBusyPositions();
    
    console.log(`Найдено активных столов: ${activeGames.length}`);
    console.log(`Занятые позиции: ${Array.from(busyPositions).map(p => p.replace('pos_', '')).join(', ') || 'нет'}`);
    
    // Ищем самую верхнюю свободную позицию
    for (let pos = 0; pos < activeGames.length; pos++) {
        if (!busyPositions.has(`pos_${pos}`)) {
            console.log(`🎯 Браузер ${browserId} выбрал позицию ${pos}`);
            return {
                position: pos,
                href: activeGames[pos].href
            };
        }
    }
    
    console.log('❌ Свободных позиций не найдено');
    return null;
}

async function getCards(page) {
    if (page.isClosed()) return { player: [], banker: [], pScore: '0', bScore: '0' };
    
    const playerBlock = await page.$('.baccarat-player:not(.baccarat-player--is-reversed) .baccarat-player__cards').catch(() => null);
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
    }).catch(() => []) : [];

    const bankerBlock = await page.$('.baccarat-player--is-reversed .baccarat-player__cards').catch(() => null);
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
    }).catch(() => []) : [];

    const pScore = await page.$eval('.baccarat-player:not(.baccarat-player--is-reversed) .baccarat-player__number', el => el.textContent).catch(() => '0');
    const bScore = await page.$eval('.baccarat-player--is-reversed .baccarat-player__number', el => el.textContent).catch(() => '0');

    return { player, banker, pScore, bScore };
}

// ===== МОНИТОРИНГ ИГРЫ =====
async function monitorGame(page, gameNumber, position) {
    console.log(`🎮 Мониторинг игры #${gameNumber} (позиция ${position})`);
    
    let lastCards = { player: [], banker: [], pScore: '0', bScore: '0' };
    
    while (true) {
        if (page.isClosed()) {
            console.log('⚠️ Страница закрыта, выход из мониторинга');
            break;
        }
        
        const cards = await getCards(page);
        
        const isGameOver = await page.evaluate(() => {
            const panel = document.querySelector('.market-grid__game-over-panel');
            return panel !== null;
        }).catch(() => false);
        
        if (isGameOver) {
            console.log('🏁 Игра завершена, проверяю карты...');
            
            let finalCards = cards;
            let retryCount = 0;
            
            while ((finalCards.player.length === 0 || finalCards.banker.length === 0) && retryCount < 5 && !page.isClosed()) {
                console.log(`⏳ Повторная попытка чтения карт (${retryCount + 1}/5)...`);
                await page.waitForTimeout(500).catch(() => {});
                finalCards = await getCards(page);
                retryCount++;
            }
            
            if (finalCards.player.length > 0 || finalCards.banker.length > 0) {
                cards.player = finalCards.player;
                cards.banker = finalCards.banker;
                cards.pScore = finalCards.pScore;
                cards.bScore = finalCards.bScore;
            }
            
            if (cards.player.length > 0 || cards.banker.length > 0 || cards.pScore !== '0' || cards.bScore !== '0') {
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
            
            await page.waitForTimeout(10000).catch(() => {});
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
        
        await page.waitForTimeout(2000).catch(() => {});
    }
}

// ===== ОСНОВНАЯ ФУНКЦИЯ =====
async function run() {
    const browserId = browserCounter++;
    let browser;
    let timeout;
    let currentPosition = null;
    const startTime = Date.now();
    
    try {
        console.log(`\n🟢 Браузер ${browserId} открыт в ${new Date().toLocaleTimeString()}.${new Date().getMilliseconds()}`);
        
        browser = await chromium.launch({ 
            headless: true,
            args: [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage'
            ]
        });
        
        const page = await browser.newPage();
        
        timeout = setTimeout(async () => {
            console.log(`⏱ Браузер ${browserId} завершает работу (4 минуты)`);
            if (currentPosition !== null) {
                markPositionFree(currentPosition);
            }
            if (browser && browser.isConnected()) {
                await browser.close().catch(() => {});
            }
        }, 240000);
        
        await page.goto(URL, { timeout: 30000, waitUntil: 'domcontentloaded' }).catch(e => {
            console.log(`❌ Ошибка загрузки страницы:`, e.message);
            return;
        });
        
        // Ищем свободную позицию
        const positionInfo = await findFreePosition(page, browserId);
        if (!positionInfo) {
            console.log(`❌ Браузер ${browserId} не нашел свободных позиций`);
            return;
        }
        
        currentPosition = positionInfo.position;
        console.log(`Браузер ${browserId} заходит в позицию ${currentPosition}:`, positionInfo.href);
        
        await page.click(`a[href="${positionInfo.href}"]`).catch(e => {
            console.log(`❌ Ошибка клика:`, e.message);
            return;
        });
        
        let gameNumber = getGameNumberByTime();
        if (!gameNumber) {
            console.log('⏰ До начала игр еще время');
            return;
        }
        
        gameNumber = gameNumber.toString();
        console.log('🎰 Номер игры:', gameNumber);
        
        lastGameNumber = gameNumber;
        fs.writeFileSync(LAST_NUMBER_FILE, gameNumber);
        
        let cardsAttempts = 0;
        let cards = { player: [], banker: [], pScore: '0', bScore: '0' };
        
        while (cardsAttempts < 12 && (cards.player.length === 0 || cards.banker.length === 0) && !page.isClosed()) {
            await page.waitForTimeout(5000).catch(() => {});
            cards = await getCards(page);
            cardsAttempts++;
            console.log(`⏳ Ожидание карт... попытка ${cardsAttempts}/12 (игрок: ${cards.player.length}, дилер: ${cards.banker.length})`);
        }
        
        if (cards.player.length > 0 && cards.banker.length > 0 && !page.isClosed()) {
            await monitorGame(page, gameNumber, currentPosition);
        } else {
            console.log('⚠️ Карты не появились за 12 попыток');
        }
        
    } catch (e) {
        console.log(`❌ Ошибка браузера ${browserId}:`, e.message);
    } finally {
        if (timeout) clearTimeout(timeout);
        if (currentPosition !== null) {
            markPositionFree(currentPosition);
        }
        if (browser && browser.isConnected()) {
            await browser.close().catch(() => {});
            console.log(`🔴 Браузер ${browserId} закрыт, проработал ${((Date.now() - startTime)/1000).toFixed(3)} секунды`);
        }
        lastMessageId = null;
        lastMessageText = '';
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
    console.log('🎯 Динамическое смещение: каждый браузер занимает верхнюю свободную позицию');
    console.log('⏱ Запуск в :58 каждой минуты');
    console.log('⏱ Жизнь браузера: 4 минуты');
    
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
        
        await new Promise(resolve => setTimeout(resolve, 60000));
    }
})();