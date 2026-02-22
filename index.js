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

// Загружаем последний номер из файла
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

// Ищем ВТОРОЙ активный стол
async function findSecondLiveGame(page) {
    const games = await page.$$('.dashboard-game');
    console.log(`Найдено столов: ${games.length}`);
    
    let activeGames = [];
    
    for (const game of games) {
        const hasTimer = await game.$('.dashboard-game-info__time') !== null;
        if (!hasTimer) continue;

        const isFinished = await game.evaluate(el => {
            const period = el.querySelector('.dashboard-game-info__period');
            return period?.textContent.includes('Игра завершена') ?? false;
        });

        if (!isFinished) {
            const link = await game.$('a[href*="/ru/live/baccarat/"]');
            if (link) {
                const href = await link.getAttribute('href');
                activeGames.push(href);
                console.log(`✅ Активный стол #${activeGames.length}`);
            }
        }
    }
    
    // Берем ВТОРОЙ стол (индекс 1)
    if (activeGames.length >= 2) {
        console.log(`🎯 Беру второй стол`);
        return activeGames[1];
    }
    
    // Если нет второго - берем первый
    if (activeGames.length === 1) {
        console.log(`⚠️ Только один активный стол, беру его`);
        return activeGames[0];
    }
    
    console.log('❌ Активных столов не найдено');
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
        
        // Проверка на завершение игры
        const isGameOver = await page.evaluate(() => {
            const panel = document.querySelector('.market-grid__game-over-panel');
            if (!panel) return false;
            const caption = panel.querySelector('.ui-caption');
            return caption && caption.textContent.includes('Игра завершена');
        });
        
        if (isGameOver) {
            const cards = await getCards(page);
            
            if (cards.player.length > 0 || cards.banker.length > 0) {
                console.log('Игра завершена, отправляю результат...');
                
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
            
            console.log('Жду 10 секунд перед закрытием...');
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

async function run() {
    let browser;
    let timeout;
    
    try {
        const startTime = new Date();
        console.log(`\n🟢 Браузер открыт в ${startTime.toLocaleTimeString()}.${startTime.getMilliseconds()}`);
        
        browser = await chromium.launch({ headless: true });
        const page = await browser.newPage();
        
        // Таймаут 3 минуты (180 секунд)
        timeout = setTimeout(async () => {
            console.log(`⏱ 3 минуты прошло, закрываю браузер`);
            if (browser) await browser.close();
        }, 180000); // 3 минуты
        
        await page.goto(URL);
        console.log('Ищем второй активный стол...');
        
        let activeLink = null;
        let attempts = 0;
        while (!activeLink && attempts < 10) {
            activeLink = await findSecondLiveGame(page);
            if (!activeLink) {
                console.log('Жду 5 секунд...');
                await page.waitForTimeout(5000);
                attempts++;
            }
        }
        
        if (!activeLink) {
            console.log('❌ Не нашел второй стол за 10 попыток');
            return;
        }
        
        console.log('Захожу во второй стол:', activeLink);
        await page.click(`a[href="${activeLink}"]`);
        await page.waitForTimeout(3000);
        
        // Получаем номер игры
        let gameNumber = await page.evaluate(() => {
            const el = document.querySelector('.dashboard-game-info__additional-info');
            return el ? el.textContent.trim() : null;
        });
        
        if (!gameNumber) {
            gameNumber = (parseInt(lastGameNumber) + 1).toString();
            console.log('Номер не найден, присваиваю:', gameNumber);
        } else {
            console.log('Номер стола:', gameNumber);
        }
        
        lastGameNumber = gameNumber;
        fs.writeFileSync(LAST_NUMBER_FILE, gameNumber);
        
        let attemptsCards = 0;
        let cards = { player: [], banker: [] };
        while (attemptsCards < 12 && (cards.player.length === 0 || cards.banker.length === 0)) {
            await page.waitForTimeout(5000);
            cards = await getCards(page);
            attemptsCards++;
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

// Запуск с интервалом
(async () => {
    console.log('🤖 Бот Baccarat запущен');
    console.log('🎯 Беру только второй активный стол');
    console.log('⏱ Время жизни браузера: 3 минуты');
    
    while (true) {
        await run();
        console.log('⏱ Жду 45 секунд до следующего запуска...\n');
        await new Promise(resolve => setTimeout(resolve, 45000));
    }
})();
